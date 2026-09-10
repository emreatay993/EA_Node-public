import QtQuick 2.15
import QtTest 1.3
import "../../ea_node_editor/ui_qml/components/graph" as Graph
import "../../ea_node_editor/ui_qml/components/shell" as Shell

TestCase {
    id: testCase
    name: "GraphNodeHost"
    width: 800
    height: 600
    visible: true
    when: windowShown
    property var tooltipCopyBridge: null
    property var uiIcons: uiIconsStub

    QtObject {
        id: uiIconsStub

        function sourceSized(name, size, color) {
            return ""
        }
    }

    Item {
        id: stage
        anchors.fill: parent
        visible: true
    }

    Component {
        id: graphNodeHostComponent
        Graph.GraphNodeHost {}
    }

    Component {
        id: libraryNodeVisualComponent
        Shell.LibraryNodeVisual {}
    }

    Component {
        id: groupCanvasProxyComponent

        Item {
            property var sceneBridge: ({
                "selected_node_lookup": {
                    "node_group_backdrop_surface_test": true
                }
            })
        }
    }

    function surfaceSpec(family, variant) {
        var componentKey = "standard"
        var qmlComponent = "GraphStandardNodeSurface.qml"
        if (family === "annotation") {
            componentKey = "annotation"
            qmlComponent = "passive/GraphAnnotationNoteSurface.qml"
        } else if (family === "planning") {
            componentKey = "planning"
            qmlComponent = "passive/GraphPlanningCardSurface.qml"
        } else if (family === "flowchart") {
            componentKey = "flowchart"
            qmlComponent = "passive/GraphFlowchartNodeSurface.qml"
        } else if (family === "group_backdrop") {
            componentKey = "group_backdrop"
            qmlComponent = "passive/GraphGroupBackdropSurface.qml"
        } else if (family === "media") {
            componentKey = "media"
            qmlComponent = "passive/GraphMediaPanelSurface.qml"
        }
        return {
            "family": family,
            "variant": variant,
            "component_key": componentKey,
            "qml_component": qmlComponent,
            "fullscreen": {},
            "input_capabilities": {
                "devices": ["mouse", "touch"],
                "events": ["press", "release", "move", "wheel"],
                "hover": true,
                "pressure": false,
                "gestures": ["tap", "drag", "wheel"],
                "plugin_gestures": []
            },
            "native_overlay": {},
            "layout": {},
            "metadata": {}
        }
    }

    function nodePayload(surfaceFamily, surfaceVariant) {
        var family = surfaceFamily === undefined ? "standard" : surfaceFamily
        var variant = surfaceVariant === undefined ? "" : surfaceVariant
        return {
            "node_id": "node_surface_host_test",
            "type_id": "core.logger",
            "title": "Logger",
            "x": 120.0,
            "y": 120.0,
            "width": 210.0,
            "height": 88.0,
            "accent": "#2F89FF",
            "collapsed": false,
            "selected": false,
            "runtime_behavior": "active",
            "surface_family": family,
            "surface_variant": variant,
            "surface_spec": surfaceSpec(family, variant),
            "surface_metrics": {
                "default_width": 210.0,
                "default_height": 88.0,
                "min_width": 120.0,
                "min_height": 50.0,
                "collapsed_width": 130.0,
                "collapsed_height": 36.0,
                "header_height": 24.0,
                "header_top_margin": 4.0,
                "body_top": 30.0,
                "body_height": 30.0,
                "port_top": 60.0,
                "port_height": 18.0,
                "port_center_offset": 6.0,
                "port_side_margin": 8.0,
                "port_dot_radius": 5.0,
                "resize_handle_size": 16.0
            },
            "visual_style": {},
            "can_enter_scope": false,
            "ports": [
                {
                    "key": "payload",
                    "label": "Payload",
                    "direction": "in",
                    "kind": "data",
                    "data_type": "any",
                    "connected": false
                },
                {
                    "key": "result",
                    "label": "Result",
                    "direction": "out",
                    "kind": "data",
                    "data_type": "any",
                    "connected": false
                }
            ],
            "inline_properties": [
                {
                    "key": "message",
                    "label": "Message",
                    "inline_editor": "text",
                    "value": "log message",
                    "overridden_by_input": false,
                    "input_port_label": "message"
                }
            ]
        }
    }

    function flowchartPayload(variant) {
        var payload = nodePayload("flowchart", variant)
        payload.runtime_behavior = "passive"
        payload.type_id = "passive.flowchart." + variant
        payload.title = "Decision"
        payload.display_name = "Decision"
        payload.properties = {
            "title": "Decision",
            "body": "Review the decision criteria and route accordingly."
        }
        payload.width = 236.0
        payload.height = 128.0
        payload.ports = [
            {"key": "top", "label": "top", "direction": "neutral", "kind": "flow", "data_type": "flow", "exposed": true, "connected": false},
            {"key": "right", "label": "right", "direction": "neutral", "kind": "flow", "data_type": "flow", "exposed": true, "connected": false},
            {"key": "bottom", "label": "bottom", "direction": "neutral", "kind": "flow", "data_type": "flow", "exposed": true, "connected": false},
            {"key": "left", "label": "left", "direction": "neutral", "kind": "flow", "data_type": "flow", "exposed": true, "connected": false}
        ]
        payload.inline_properties = []
        return payload
    }

    function cardinalPassivePorts() {
        return [
            {"key": "top", "label": "top", "direction": "neutral", "kind": "flow", "data_type": "flow", "side": "top", "exposed": true, "allow_multiple_connections": true, "connected": false},
            {"key": "right", "label": "right", "direction": "neutral", "kind": "flow", "data_type": "flow", "side": "right", "exposed": true, "allow_multiple_connections": true, "connected": false},
            {"key": "bottom", "label": "bottom", "direction": "neutral", "kind": "flow", "data_type": "flow", "side": "bottom", "exposed": true, "allow_multiple_connections": true, "connected": false},
            {"key": "left", "label": "left", "direction": "neutral", "kind": "flow", "data_type": "flow", "side": "left", "exposed": true, "allow_multiple_connections": true, "connected": false}
        ]
    }

    function passiveSurfacePayload(family, variant, title, properties, width, height) {
        var payload = nodePayload(family, variant)
        payload.node_id = "node_planning_annotation_surface_test"
        payload.type_id = "tests.passive_surface"
        payload.title = title
        payload.properties = properties
        payload.width = width
        payload.height = height
        payload.runtime_behavior = "passive"
        payload.ports = cardinalPassivePorts()
        payload.inline_properties = []
        return payload
    }

    function bareTextSurfaceSpec() {
        return {
            "family": "annotation",
            "variant": "text",
            "component_key": "annotation_text",
            "qml_component": "passive/GraphBareTextSurface.qml",
            "fullscreen": {
                "supported": false,
                "content_kind": "",
                "action_id": "fullscreen",
                "action_label": "Fullscreen",
                "action_icon": "fullscreen",
                "action_kind": "surface",
                "requires_bridge": true
            },
            "input_capabilities": {
                "devices": ["mouse", "touch"],
                "events": ["press", "release", "move", "wheel"],
                "hover": true,
                "pressure": false,
                "gestures": ["tap", "drag", "wheel"],
                "plugin_gestures": []
            },
            "native_overlay": {"required": false, "target": "", "owner": ""},
            "layout": {
                "content_region": "host",
                "min_body_width": 0,
                "min_body_height": 0,
                "preferred_body_height": 0
            },
            "metadata": {"bare_text": true}
        }
    }

    function groupBackdropPayload(properties) {
        var payload = nodePayload("group_backdrop", "group_backdrop")
        payload.node_id = "node_group_backdrop_surface_test"
        payload.type_id = "passive.annotation.group_backdrop"
        payload.title = String(properties.title || "")
        payload.x = 120
        payload.y = 90
        payload.width = 420
        payload.height = 260
        payload.runtime_behavior = "passive"
        payload.ports = cardinalPassivePorts()
        payload.inline_properties = []
        payload.properties = properties
        payload.surface_metrics = {
            "default_width": 420,
            "default_height": 260,
            "min_width": 260,
            "min_height": 180,
            "collapsed_width": 130,
            "collapsed_height": 36,
            "header_height": 0,
            "header_top_margin": 0,
            "body_top": 52,
            "body_height": 190,
            "port_top": 242,
            "port_height": 0,
            "port_center_offset": 0,
            "port_side_margin": 8,
            "port_dot_radius": 5,
            "resize_handle_size": 16,
            "title_top": 14,
            "title_height": 24,
            "title_left_margin": 18,
            "title_right_margin": 18,
            "title_centered": false,
            "body_left_margin": 18,
            "body_right_margin": 18,
            "body_bottom_margin": 18,
            "use_host_chrome": false,
            "use_host_shadow": false
        }
        return payload
    }

    function appendNamedItems(rootItem, objectName, matches) {
        if (!rootItem)
            return
        if (rootItem.objectName === objectName)
            matches.push(rootItem)
        var children = rootItem.children || []
        for (var index = 0; index < children.length; ++index)
            appendNamedItems(children[index], objectName, matches)
    }

    function findNamedItems(rootItem, objectName) {
        var matches = []
        appendNamedItems(rootItem, objectName, matches)
        return matches
    }

    function t21Hash(text) {
        var hash = 2166136261
        var value = String(text || "")
        for (var index = 0; index < value.length; ++index) {
            hash ^= value.charCodeAt(index)
            hash = Math.imul(hash, 16777619)
        }
        return (hash >>> 0).toString(16).padStart(8, "0")
    }

    function t21ClassName(item) {
        var value = String(item || "")
        var splitIndex = value.indexOf("(")
        var className = splitIndex >= 0 ? value.slice(0, splitIndex) : value
        return className
            .replace(/_QMLTYPE_[0-9]+/g, "_QMLTYPE")
            .replace(/_QML_[0-9]+/g, "_QML")
    }

    function t21Descendants(item, result) {
        var children = item && item.children ? item.children : []
        for (var index = 0; index < children.length; ++index) {
            result.push(children[index])
            t21Descendants(children[index], result)
        }
    }

    function t21Rounded(value) {
        var numeric = Number(value || 0)
        return isFinite(numeric) ? numeric.toFixed(3) : "nan"
    }

    function t21RowTopology(row) {
        var descendants = []
        t21Descendants(row, descendants)
        var records = []
        var geometryRecords = []
        var canvasCount = 0
        var loaderCount = 0
        for (var index = 0; index < descendants.length; ++index) {
            var item = descendants[index]
            var className = t21ClassName(item)
            var name = String(item.objectName || "")
            var parentName = String(item.parent && item.parent.objectName || "")
            records.push([className, name, parentName].join("|"))
            if (className.indexOf("Canvas") >= 0)
                canvasCount += 1
            if (className.indexOf("Loader") >= 0)
                loaderCount += 1
            if (name.length > 0) {
                geometryRecords.push([
                    name,
                    parentName,
                    t21Rounded(item.x),
                    t21Rounded(item.y),
                    t21Rounded(item.width),
                    t21Rounded(item.height),
                    item.visible ? "1" : "0"
                ].join("|"))
            }
        }
        records.sort()
        geometryRecords.sort()
        var rects = row.currentEmbeddedInteractiveRects
            ? row.currentEmbeddedInteractiveRects()
            : []
        return {
            "topology_hash": t21Hash(records.join("\n")),
            "geometry_hash": t21Hash([
                geometryRecords.join("\n"),
                t21Rounded(row.portPoint ? row.portPoint.x : 0),
                t21Rounded(row.portPoint ? row.portPoint.y : 0),
                JSON.stringify(rects)
            ].join("\n")),
            "qquickitem_count": descendants.length + 1,
            "qobject_count": descendants.length + 1,
            "loader_count": loaderCount,
            "canvas_count": canvasCount,
            "connection_count": 0,
            "binding_count": 0,
            "qtimer_count": 0,
            "padlock_count": findNamedItems(row, row.propertyKey === "payload"
                ? "graphNodeInputPortPadlock"
                : "graphNodeOutputPortPadlock").length,
            "default_count": findNamedItems(row, "graphNodeInputDefaultProperty").length,
            "slash_count": findNamedItems(row, "graphNodeInputPortInactiveSlash").length
        }
    }

    function t21PortPayload() {
        var payload = nodePayload()
        payload.node_id = "node_t21_port_topology"
        payload.ports[0].flow_state = "default"
        payload.ports[0].default_property = {
            "key": "payload",
            "label": "Payload",
            "type": "str",
            "value": "default text",
            "display_value": "default text",
            "display_value_available": true,
            "inline_editor": "text",
            "overridden_by_input": false,
            "editor_enabled": true,
            "condition_enabled": true
        }
        return payload
    }

    function createHost(payload, properties) {
        var values = properties || {}
        values.nodeData = payload
        return createTemporaryObject(graphNodeHostComponent, stage, values)
    }

    function allVisible(items, expected) {
        for (var index = 0; index < items.length; ++index) {
            if (Boolean(items[index].visible) !== expected)
                return false
        }
        return true
    }

    function visibleWithin(item, rootItem) {
        var current = item
        while (current) {
            if (!current.visible)
                return false
            if (current === rootItem)
                return true
            current = current.parent
        }
        return false
    }

    function test_graph_node_host_loads_standard_surface_for_standard_nodes() {
        var host = createHost(nodePayload())
        verify(host !== null)
        compare(host.objectName, "graphNodeCard")
        compare(host.surfaceFamily, "standard")
        tryVerify(function() { return findNamedItems(host, "graphNodeSurfaceLoader").length === 1 })
        var loader = findNamedItems(host, "graphNodeSurfaceLoader")[0]
        tryCompare(loader, "loadedSurfaceKey", "standard")
        tryVerify(function() { return findNamedItems(host, "graphNodeStandardSurface").length === 1 })
    }

    function test_graph_node_host_uses_surface_spec_for_standard_surface_selection() {
        var payload = nodePayload("media", "image_panel")
        payload.surface_spec = surfaceSpec("standard", "")
        var host = createHost(payload)
        verify(host !== null)
        compare(host.surfaceFamily, "standard")
        compare(host.surfaceVariant, "image_panel")
        tryVerify(function() { return findNamedItems(host, "graphNodeSurfaceLoader").length === 1 })
        var loader = findNamedItems(host, "graphNodeSurfaceLoader")[0]
        tryCompare(loader, "loadedSurfaceKey", "standard")
        compare(JSON.stringify(loader.inputCapabilities.devices), JSON.stringify(["mouse", "touch"]))
        tryVerify(function() { return findNamedItems(host, "graphNodeStandardSurface").length === 1 })

        var fallbackPayload = nodePayload("media", "")
        delete fallbackPayload.surface_spec
        var fallbackHost = createHost(fallbackPayload)
        verify(fallbackHost !== null)
        compare(fallbackHost.surfaceFamily, "standard")
        compare(fallbackHost.surfaceVariant, "")
        tryVerify(function() { return findNamedItems(fallbackHost, "graphNodeSurfaceLoader").length === 1 })
        var fallbackLoader = findNamedItems(fallbackHost, "graphNodeSurfaceLoader")[0]
        tryCompare(fallbackLoader, "loadedSurfaceKey", "standard")
        tryVerify(function() { return findNamedItems(fallbackHost, "graphNodeStandardSurface").length === 1 })
    }

    function test_graph_node_host_uses_curve_rendering_for_node_text() {
        var standardHost = createHost(nodePayload())
        verify(standardHost !== null)
        tryVerify(function() {
            return findNamedItems(standardHost, "graphNodeTitle").length === 1
                && findNamedItems(standardHost, "graphNodeInputPortLabel").length >= 1
        })
        var titleItem = findNamedItems(standardHost, "graphNodeTitle")[0]
        var inputLabels = findNamedItems(standardHost, "graphNodeInputPortLabel")
        compare(titleItem.effectiveRenderType, standardHost.nodeTextRenderType)
        compare(inputLabels[0].effectiveRenderType, standardHost.nodeTextRenderType)

        var annotationPayload = nodePayload("annotation", "sticky_note")
        annotationPayload.runtime_behavior = "passive"
        annotationPayload.properties = {"body": "Sticky note"}
        var annotationHost = createHost(annotationPayload)
        verify(annotationHost !== null)
        tryVerify(function() { return findNamedItems(annotationHost, "graphNodeAnnotationBodyText").length === 1 })
        var annotationText = findNamedItems(annotationHost, "graphNodeAnnotationBodyText")[0]
        compare(annotationText.effectiveRenderType, annotationHost.nodeTextRenderType)

        var planningPayload = nodePayload("planning", "task_card")
        planningPayload.runtime_behavior = "passive"
        planningPayload.properties = {
            "body": "Follow up with render pass",
            "status": "in progress",
            "owner": "Alex",
            "due_date": "Tomorrow"
        }
        var planningHost = createHost(planningPayload)
        verify(planningHost !== null)
        tryVerify(function() { return findNamedItems(planningHost, "graphNodePlanningBodyText").length === 1 })
        var planningText = findNamedItems(planningHost, "graphNodePlanningBodyText")[0]
        compare(planningText.effectiveRenderType, planningHost.nodeTextRenderType)
    }

    function test_port_row_topology_and_directional_children_stay_stable() {
        var unlockedHost = createHost(t21PortPayload())
        verify(unlockedHost !== null)
        tryVerify(function() {
            return findNamedItems(unlockedHost, "graphNodeInputPortRow").length === 1
                && findNamedItems(unlockedHost, "graphNodeOutputPortRow").length === 1
        })
        var lockedPayload = t21PortPayload()
        lockedPayload.unresolved = true
        lockedPayload.locked_state = {"reason": "Missing add-on"}
        var lockedHost = createHost(lockedPayload, {"graphReadOnly": true})
        verify(lockedHost !== null)
        tryVerify(function() {
            return findNamedItems(lockedHost, "graphNodeInputPortRow").length === 1
                && findNamedItems(lockedHost, "graphNodeOutputPortRow").length === 1
                && findNamedItems(lockedHost, "graphNodeOutputPortPadlock").length === 1
        })

        var unlockedInput = findNamedItems(unlockedHost, "graphNodeInputPortRow")[0]
        var unlockedOutput = findNamedItems(unlockedHost, "graphNodeOutputPortRow")[0]
        var lockedInput = findNamedItems(lockedHost, "graphNodeInputPortRow")[0]
        var lockedOutput = findNamedItems(lockedHost, "graphNodeOutputPortRow")[0]
        var snapshot = {
            "unlocked_input": t21RowTopology(unlockedInput),
            "unlocked_output": t21RowTopology(unlockedOutput),
            "locked_input": t21RowTopology(lockedInput),
            "locked_output": t21RowTopology(lockedOutput)
        }
        var expected = {
            "unlocked_input": {
                "topology_hash": "d0078e01",
                "geometry_hash": "598ed08e",
                "qquickitem_count": 135,
                "loader_count": 0,
                "canvas_count": 1
            },
            "unlocked_output": {
                "topology_hash": "55b1e6c7",
                "geometry_hash": "bb892984",
                "qquickitem_count": 21,
                "loader_count": 1,
                "canvas_count": 0
            },
            "locked_input": {
                "topology_hash": "ee335365",
                "geometry_hash": "68a714d3",
                "qquickitem_count": 25,
                "loader_count": 0,
                "canvas_count": 1
            },
            "locked_output": {
                "topology_hash": "2fccbe03",
                "geometry_hash": "f942da05",
                "qquickitem_count": 22,
                "loader_count": 1,
                "canvas_count": 1
            }
        }
        for (var stateName in expected) {
            compare(snapshot[stateName].topology_hash, expected[stateName].topology_hash)
            compare(snapshot[stateName].geometry_hash, expected[stateName].geometry_hash)
            compare(snapshot[stateName].qquickitem_count, expected[stateName].qquickitem_count)
            compare(snapshot[stateName].qobject_count, expected[stateName].qquickitem_count)
            compare(snapshot[stateName].loader_count, expected[stateName].loader_count)
            compare(snapshot[stateName].canvas_count, expected[stateName].canvas_count)
            compare(snapshot[stateName].connection_count, 0)
            compare(snapshot[stateName].binding_count, 0)
            compare(snapshot[stateName].qtimer_count, 0)
        }

        compare(snapshot.unlocked_input.padlock_count, 1)
        compare(snapshot.unlocked_input.default_count, 1)
        compare(snapshot.unlocked_input.slash_count, 1)
        compare(snapshot.unlocked_output.padlock_count, 0)
        compare(snapshot.unlocked_output.default_count, 0)
        compare(snapshot.unlocked_output.slash_count, 0)
        compare(snapshot.locked_input.padlock_count, 1)
        compare(snapshot.locked_output.padlock_count, 1)
        compare(snapshot.unlocked_output.loader_count, 1)
        compare(snapshot.locked_output.loader_count, 1)
        compare(unlockedInput.direction, "in")
        compare(unlockedOutput.direction, "out")
        compare(
            findNamedItems(unlockedInput, "graphNodeInputPortInactiveSlash")[0].parent,
            findNamedItems(unlockedInput, "graphNodeInputPortDot")[0]
        )
        compare(
            findNamedItems(unlockedInput, "graphNodeInputDefaultProperty")[0].parent,
            unlockedInput
        )
        compare(
            findNamedItems(lockedInput, "graphNodeInputPortPadlock")[0].parent,
            findNamedItems(lockedInput, "graphNodeInputPortDot")[0]
        )
        compare(
            findNamedItems(lockedOutput, "graphNodeOutputPortPadlock")[0].parent.parent,
            findNamedItems(lockedOutput, "graphNodeOutputPortDot")[0]
        )
        var inputNotch = findNamedItems(unlockedInput, "graphNodeInputPortNotch")[0]
        var outputNotch = findNamedItems(unlockedOutput, "graphNodeOutputPortNotch")[0]
        compare(inputNotch.width, 9)
        compare(inputNotch.height, 18)
        compare(outputNotch.width, 9)
        compare(outputNotch.height, 18)
        verify(!inputNotch.mirror)
        verify(outputNotch.mirror)
        verify(inputNotch.cache)
        verify(outputNotch.cache)
    }

    function test_port_row_default_editor_stays_visible_when_overridden() {
        var authoredHost = createHost(t21PortPayload())
        verify(authoredHost !== null)
        tryVerify(function() {
            return findNamedItems(authoredHost, "graphNodeInputDefaultProperty").length === 1
        })
        var authoredRow = findNamedItems(authoredHost, "graphNodeInputPortRow")[0]
        var authoredLayer = findNamedItems(authoredHost, "graphNodeInputDefaultProperty")[0]
        verify(authoredRow.defaultEditorVisible)
        verify(authoredLayer.visible)
        verify(authoredLayer.enabled)

        var overriddenPayload = t21PortPayload()
        overriddenPayload.ports[0].connected = true
        overriddenPayload.ports[0].flow_state = "active"
        overriddenPayload.ports[0].default_property.overridden_by_input = true
        var overriddenHost = createHost(overriddenPayload)
        verify(overriddenHost !== null)
        tryVerify(function() {
            return findNamedItems(overriddenHost, "graphNodeInputDefaultProperty").length === 1
        })
        var overriddenRow = findNamedItems(overriddenHost, "graphNodeInputPortRow")[0]
        var overriddenLayer = findNamedItems(overriddenHost, "graphNodeInputDefaultProperty")[0]
        verify(overriddenRow.defaultEditorVisible)
        verify(overriddenLayer.visible)
        compare(overriddenRow.currentEmbeddedInteractiveRects().length, 0)
    }

    function test_port_row_consumes_flow_type_tooltip_and_accessibility_facts() {
        var payload = t21PortPayload()
        payload.ports[0].data_type_label = "Text"
        payload.ports[0].description = "Message payload"
        payload.ports[0].flow_state = "invalid"
        payload.ports[0].data_type_warning = true
        payload.ports[1].inactive = true
        payload.ports[1].inactive_reason = "Output is unavailable"
        var host = createHost(payload)
        verify(host !== null)
        tryVerify(function() {
            return findNamedItems(host, "graphNodeInputPortMouseArea").length === 1
                && findNamedItems(host, "graphNodeOutputPortMouseArea").length === 1
                && findNamedItems(host, "graphNodeOutputPortPadlock").length === 1
        })
        var inputDot = findNamedItems(host, "graphNodeInputPortDot")[0]
        var inputMouse = findNamedItems(host, "graphNodeInputPortMouseArea")[0]
        var outputDot = findNamedItems(host, "graphNodeOutputPortDot")[0]
        var outputMouse = findNamedItems(host, "graphNodeOutputPortMouseArea")[0]
        compare(inputDot.interactionDirection, "in")
        compare(outputDot.interactionDirection, "out")
        compare(String(inputDot.color).toLowerCase(), "#ff543e")
        verify(inputMouse.accessiblePortText.indexOf("Payload") >= 0)
        verify(inputMouse.accessiblePortText.indexOf("Text") >= 0)
        verify(inputMouse.portHelpTooltipText.length > 0)
        verify(outputDot.inactiveState)
        verify(outputDot.lockedState)
        compare(outputMouse.inactiveTooltipText, "Output is unavailable")
        compare(outputMouse.cursorShape, Qt.ForbiddenCursor)
    }

    function test_port_row_dynamic_remove_and_label_edit_keep_directional_geometry() {
        var payload = nodePayload()
        payload.node_id = "node_t21_dynamic_port_row"
        payload.dynamic_port_groups = [
            {
                "id": "inputs",
                "direction": "in",
                "port_keys": ["payload"],
                "can_insert": true,
                "removable_port_keys": ["payload"],
                "rename_mode": "label"
            },
            {
                "id": "outputs",
                "direction": "out",
                "port_keys": ["result"],
                "can_insert": true,
                "removable_port_keys": ["result"],
                "rename_mode": "label"
            }
        ]
        var host = createHost(payload)
        verify(host !== null)
        var inputRow = findNamedItems(host, "graphNodeInputPortRow")[0]
        var outputRow = findNamedItems(host, "graphNodeOutputPortRow")[0]
        mouseMove(inputRow, inputRow.portPoint.x, inputRow.height * 0.5)
        tryVerify(function() {
            var controls = findNamedItems(host, "graphNodeDynamicPortRemove_payload")
            return controls.length === 1 && controls[0].visible
        })
        var inputRemove = findNamedItems(host, "graphNodeDynamicPortRemove_payload")[0]
        compare(
            t21Rounded(inputRemove.x + inputRemove.width * 0.5 - inputRow.portPoint.x),
            t21Rounded(9)
        )
        compare(inputRemove.propertyKey, "payload")
        var inputLabel = findNamedItems(host, "graphNodeInputPortLabel")[0]
        compare(
            t21Rounded(inputLabel.parent.x - (inputRemove.x + inputRemove.width)),
            t21Rounded(0)
        )
        compare(inputRemove.tooltipText, "Remove input")

        mouseMove(outputRow, outputRow.portPoint.x, outputRow.height * 0.5)
        tryVerify(function() {
            var controls = findNamedItems(host, "graphNodeDynamicPortRemove_result")
            return controls.length === 1 && controls[0].visible
        })
        var outputRemove = findNamedItems(host, "graphNodeDynamicPortRemove_result")[0]
        compare(
            t21Rounded(outputRow.portPoint.x - (outputRemove.x + outputRemove.width * 0.5)),
            t21Rounded(9)
        )
        compare(outputRemove.propertyKey, "result")
        var outputLabel = findNamedItems(host, "graphNodeOutputPortLabel")[0]
        compare(
            t21Rounded(outputRemove.x - (outputLabel.parent.x + outputLabel.parent.width)),
            t21Rounded(0)
        )
        compare(outputRemove.tooltipText, "Remove output")

        var portsLayer = findNamedItems(host, "graphNodePortsLayer")[0]
        portsLayer.beginPortLabelEdit("payload", "in")
        var inputEditor = findNamedItems(host, "graphNodeInputPortLabelEditor")[0]
        tryVerify(function() { return inputEditor.visible && inputEditor.activeFocus })
        compare(inputEditor.horizontalAlignment, TextInput.AlignLeft)
        portsLayer.cancelPortLabelEdit()
        tryVerify(function() { return !inputEditor.visible })

        portsLayer.beginPortLabelEdit("result", "out")
        var outputEditor = findNamedItems(host, "graphNodeOutputPortLabelEditor")[0]
        tryVerify(function() { return outputEditor.visible && outputEditor.activeFocus })
        compare(outputEditor.horizontalAlignment, TextInput.AlignRight)
        portsLayer.cancelPortLabelEdit()
        tryVerify(function() { return !outputEditor.visible })
    }

    function test_graph_node_host_exposes_split_helper_layers_with_stable_stacking() {
        var host = createHost(nodePayload())
        verify(host !== null)
        tryVerify(function() {
            return findNamedItems(host, "graphNodeChromeBackgroundLayer").length === 1
                && findNamedItems(host, "graphNodeHeaderLayer").length === 1
                && findNamedItems(host, "graphNodeHostGestureLayer").length === 1
                && findNamedItems(host, "graphNodePortsLayer").length === 1
                && findNamedItems(host, "graphNodeResizeHandle").length === 4
                && findNamedItems(host, "graphNodeDragArea").length === 1
                && findNamedItems(host, "graphNodeSurfaceLoader").length === 1
        })
        var backgroundLayer = findNamedItems(host, "graphNodeChromeBackgroundLayer")[0]
        var headerLayer = findNamedItems(host, "graphNodeHeaderLayer")[0]
        var gestureLayer = findNamedItems(host, "graphNodeHostGestureLayer")[0]
        var portsLayer = findNamedItems(host, "graphNodePortsLayer")[0]
        var resizeHandles = findNamedItems(host, "graphNodeResizeHandle")
        var dragArea = findNamedItems(host, "graphNodeDragArea")[0]
        var loader = findNamedItems(host, "graphNodeSurfaceLoader")[0]
        var roles = []
        for (var index = 0; index < resizeHandles.length; ++index)
            roles.push(String(resizeHandles[index].cornerRole))
        roles.sort()
        compare(roles.join(","), "bottomLeft,bottomRight,topLeft,topRight")
        compare(dragArea.parent.objectName, "graphNodeHostGestureLayer")
        var surfaceLayer = loader.parent
        verify(surfaceLayer !== null)
        verify(backgroundLayer.z < surfaceLayer.z)
        verify(gestureLayer.z < surfaceLayer.z)
        verify(headerLayer.z > surfaceLayer.z)
        verify(portsLayer.z > headerLayer.z)
        for (var handleIndex = 0; handleIndex < resizeHandles.length; ++handleIndex)
            verify(resizeHandles[handleIndex].z > portsLayer.z)
    }

    function test_graph_node_host_render_quality_contract_exposes_reduced_quality_tier() {
        var payload = nodePayload()
        payload.render_quality = {
            "supported_quality_tiers": ["full", "reduced"]
        }
        var host = createHost(payload, {
            "snapshotReuseActive": true
        })
        verify(host !== null)
        tryVerify(function() {
            return findNamedItems(host, "graphNodeSurfaceLoader").length === 1
                && findNamedItems(host, "graphNodeStandardSurface").length === 1
        })
        var loader = findNamedItems(host, "graphNodeSurfaceLoader")[0]
        var surface = findNamedItems(host, "graphNodeStandardSurface")[0]
        var renderQuality = host.renderQuality
        compare(Object.keys(renderQuality).sort().join(","), "supported_quality_tiers")
        compare(JSON.stringify(renderQuality.supported_quality_tiers), JSON.stringify(["full", "reduced"]))
        compare(JSON.stringify(loader.renderQuality), JSON.stringify(renderQuality))
        compare(host.requestedQualityTier, "reduced")
        compare(host.resolvedQualityTier, "reduced")
        verify(!host.proxySurfaceRequested)
        compare(loader.requestedQualityTier, "reduced")
        compare(loader.resolvedQualityTier, "reduced")
        verify(!loader.proxySurfaceRequested)
        verify(!loader.proxySurfaceActive)
        compare(host.surfaceQualityContext.requested_quality_tier, "reduced")
        compare(host.surfaceQualityContext.resolved_quality_tier, "reduced")
        verify(!host.surfaceQualityContext.proxy_surface_requested)
        compare(loader.surfaceQualityContext.resolved_quality_tier, "reduced")
        compare(surface.host.resolvedQualityTier, "reduced")
    }

    function test_standard_data_ports_remain_visible_without_hover() {
        mouseMove(stage, 1, 1)
        var host = createHost(nodePayload())
        verify(host !== null)
        tryVerify(function() {
            return findNamedItems(host, "graphNodeInputPortDot").length >= 1
                && findNamedItems(host, "graphNodeOutputPortDot").length >= 1
        })
        tryCompare(host, "hoverActive", false)
        verify(findNamedItems(host, "graphNodeInputPortDot")[0].opacity > 0.99)
        verify(findNamedItems(host, "graphNodeOutputPortDot")[0].opacity > 0.99)
    }

    function test_active_invalid_input_grip_uses_coral_without_changing_passive_palette() {
        var activePayload = nodePayload()
        activePayload.ports[0].flow_state = "invalid"
        var activeHost = createHost(activePayload)
        verify(activeHost !== null)
        tryVerify(function() { return findNamedItems(activeHost, "graphNodeInputPortDot").length >= 1 })
        var activeDot = findNamedItems(activeHost, "graphNodeInputPortDot")[0]
        compare(String(activeDot.color).toLowerCase(), "#ff543e")
        compare(String(activeDot.border.color).toLowerCase(), "#ff543e")

        var compileOnlyPayload = nodePayload()
        compileOnlyPayload.x = 350.0
        compileOnlyPayload.runtime_behavior = "compile_only"
        compileOnlyPayload.ports[0].flow_state = "invalid"
        var compileOnlyHost = createHost(compileOnlyPayload)
        verify(compileOnlyHost !== null)
        tryVerify(function() { return findNamedItems(compileOnlyHost, "graphNodeInputPortDot").length >= 1 })
        var compileOnlyDot = findNamedItems(compileOnlyHost, "graphNodeInputPortDot")[0]
        compare(String(compileOnlyDot.color).toLowerCase(), "#ff543e")
        compare(String(compileOnlyDot.border.color).toLowerCase(), "#ff543e")

        var passivePayload = nodePayload()
        passivePayload.y = 300.0
        passivePayload.runtime_behavior = "passive"
        passivePayload.ports[0].flow_state = "invalid"
        var passiveHost = createHost(passivePayload)
        verify(passiveHost !== null)
        tryVerify(function() { return findNamedItems(passiveHost, "graphNodeInputPortDot").length >= 1 })
        var passiveDot = findNamedItems(passiveHost, "graphNodeInputPortDot")[0]
        compare(String(passiveDot.color).toLowerCase(), "#d94f4f")
        compare(String(passiveDot.border.color).toLowerCase(), "#ff8c74")
    }

    function test_standard_data_grip_grows_on_real_pointer_hover_and_keeps_halo() {
        mouseMove(stage, 1, 1)
        var host = createHost(nodePayload())
        verify(host !== null)
        tryVerify(function() {
            return findNamedItems(host, "graphNodeOutputPortDot").length >= 1
                && findNamedItems(host, "graphNodeOutputPortMouseArea").length >= 1
                && findNamedItems(host, "graphNodeOutputPortRing").length >= 1
        })
        var dot = findNamedItems(host, "graphNodeOutputPortDot")[0]
        var mouseArea = findNamedItems(host, "graphNodeOutputPortMouseArea")[0]
        var ring = findNamedItems(host, "graphNodeOutputPortRing")[0]
        var restDiameter = dot.width
        host.portHoverChanged.connect(function(nodeId, portKey, direction, sceneX, sceneY, hovered) {
            host.hoveredPort = hovered
                ? {"node_id": nodeId, "port_key": portKey, "direction": direction}
                : null
        })

        mouseMove(host, host.width * 0.5, host.height * 0.5)
        tryVerify(function() { return host.hoverActive })
        var hoverPoint = mouseArea.mapToItem(
            stage,
            mouseArea.width * 0.5 - 4,
            mouseArea.height * 0.5
        )
        mouseMove(stage, hoverPoint.x, hoverPoint.y)

        tryVerify(function() { return dot.hoveredState })
        tryVerify(function() { return dot.width > restDiameter })
        verify(ring.visible)
        verify(ring.width > dot.width)

        mouseMove(stage, 1, 1)
        tryVerify(function() { return !dot.hoveredState })
        tryCompare(dot, "width", restDiameter)
    }

    function test_flow_edge_ports_reveal_on_hover_and_pending_connection_only() {
        mouseMove(stage, 1, 1)
        var host = createHost(flowchartPayload("decision"))
        verify(host !== null)
        tryVerify(function() {
            return findNamedItems(host, "graphNodeInputPortDot").length >= 1
                && findNamedItems(host, "graphNodeOutputPortDot").length >= 1
        })
        var inputDot = findNamedItems(host, "graphNodeInputPortDot")[0]
        var outputDot = findNamedItems(host, "graphNodeOutputPortDot")[0]
        tryVerify(function() { return inputDot.opacity < 0.01 && outputDot.opacity < 0.01 })

        host.pendingPort = {
            "node_id": "node_surface_host_test",
            "port_key": "top",
            "direction": "neutral"
        }
        tryVerify(function() { return inputDot.opacity > 0.99 && outputDot.opacity < 0.01 })

        host.pendingPort = null
        tryVerify(function() { return inputDot.opacity < 0.01 && outputDot.opacity < 0.01 })

        mouseMove(host, host.width * 0.5, host.height * 0.5)
        tryVerify(function() { return host.hoverActive })
        tryVerify(function() { return inputDot.opacity > 0.99 && outputDot.opacity > 0.99 })
    }

    function test_graph_node_host_shadow_cache_key_ignores_viewport_activity_but_tracks_geometry_and_shadow_preferences() {
        var host = createHost(nodePayload(), {"showShadow": true})
        verify(host !== null)
        tryVerify(function() {
            return findNamedItems(host, "graphNodeChromeBackgroundLayer").length === 1
                && findNamedItems(host, "graphNodeShadow").length === 1
                && findNamedItems(host, "graphNodeChrome").length === 1
        })
        var backgroundLayer = findNamedItems(host, "graphNodeChromeBackgroundLayer")[0]
        var shadowItem = findNamedItems(host, "graphNodeShadow")[0]
        var chromeItem = findNamedItems(host, "graphNodeChrome")[0]
        tryVerify(function() {
            return backgroundLayer.cacheActive
                && backgroundLayer.chromeCacheActive
                && backgroundLayer.shadowCacheActive
                && chromeItem.visible
                && shadowItem.cached
        })
        var baselineKey = String(backgroundLayer.cacheKey || "")
        verify(baselineKey.length > 0)

        host.viewportInteractionCacheActive = true
        tryCompare(backgroundLayer, "cacheKey", baselineKey)
        host.snapshotReuseActive = true
        tryCompare(backgroundLayer, "cacheKey", baselineKey)

        host._liveWidth = 244.0
        host._liveHeight = 96.0
        host._liveGeometryActive = true
        tryVerify(function() { return String(backgroundLayer.cacheKey || "") !== baselineKey })
        var geometryKey = String(backgroundLayer.cacheKey || "")

        host._liveGeometryActive = false
        host.shadowStrength = 55
        tryVerify(function() {
            var key = String(backgroundLayer.cacheKey || "")
            return key !== baselineKey && key !== geometryKey
        })
    }

    function test_graph_node_host_shows_resize_handles_only_for_passive_expanded_nodes() {
        mouseMove(stage, 1, 1)
        var activePayload = nodePayload()
        activePayload.x = 20.0
        var activeHost = createHost(activePayload)
        verify(activeHost !== null)
        var activeHandles = findNamedItems(activeHost, "graphNodeResizeHandle")
        compare(activeHandles.length, 4)
        mouseMove(activeHost, 84.0, 40.0)
        tryVerify(function() { return activeHost.hoverActive })
        verify(allVisible(activeHandles, false))

        var compileOnlyPayload = nodePayload()
        compileOnlyPayload.x = 290.0
        compileOnlyPayload.runtime_behavior = "compile_only"
        var compileOnlyHost = createHost(compileOnlyPayload)
        verify(compileOnlyHost !== null)
        var compileOnlyHandles = findNamedItems(compileOnlyHost, "graphNodeResizeHandle")
        compare(compileOnlyHandles.length, 4)
        mouseMove(compileOnlyHost, 84.0, 40.0)
        tryVerify(function() { return compileOnlyHost.hoverActive })
        verify(allVisible(compileOnlyHandles, false))

        var passivePayload = nodePayload()
        passivePayload.x = 560.0
        passivePayload.type_id = "tests.passive.resize"
        passivePayload.runtime_behavior = "passive"
        var passiveHost = createHost(passivePayload)
        verify(passiveHost !== null)
        var passiveHandles = findNamedItems(passiveHost, "graphNodeResizeHandle")
        compare(passiveHandles.length, 4)
        verify(allVisible(passiveHandles, false))
        mouseMove(passiveHost, 84.0, 40.0)
        tryVerify(function() { return passiveHost.hoverActive })
        tryVerify(function() { return allVisible(passiveHandles, true) })
    }

    function test_graph_node_host_keeps_resize_handles_hidden_for_collapsed_nodes() {
        mouseMove(stage, 1, 1)
        var payload = nodePayload()
        payload.type_id = "tests.passive.collapsed"
        payload.runtime_behavior = "passive"
        payload.collapsed = true
        var host = createHost(payload)
        verify(host !== null)
        tryVerify(function() { return findNamedItems(host, "graphNodeResizeHandle").length === 4 })
        var resizeHandles = findNamedItems(host, "graphNodeResizeHandle")

        mouseMove(host, 24.0, 18.0)
        tryVerify(function() { return host.hoverActive })
        tryVerify(function() { return allVisible(resizeHandles, false) })
    }

    function test_graph_node_host_loads_flowchart_surface_family() {
        var payload = flowchartPayload("decision")
        payload.title = "Flowchart"
        payload.display_name = "Flowchart"
        payload.properties = {
            "title": "Flowchart",
            "body": "Review request routing and approval outcomes."
        }
        var host = createHost(payload)
        verify(host !== null)
        tryVerify(function() {
            return findNamedItems(host, "graphNodeSurfaceLoader").length === 1
                && findNamedItems(host, "graphNodeTitle").length === 1
                && findNamedItems(host, "graphNodeFlowchartBodyText").length === 1
                && findNamedItems(host, "graphNodeFlowchartSurface").length === 1
        })
        var loader = findNamedItems(host, "graphNodeSurfaceLoader")[0]
        var titleItem = findNamedItems(host, "graphNodeTitle")[0]
        var bodyText = findNamedItems(host, "graphNodeFlowchartBodyText")[0]
        tryCompare(loader, "loadedSurfaceKey", "flowchart")
        verify(!host._useHostChrome)
        verify(!titleItem.visible)
        verify(bodyText.visible)
        compare(bodyText.text, "Review request routing and approval outcomes.")
        verify(findNamedItems(host, "graphFlowchartSilhouette").length >= 1)
        compare(findNamedItems(host, "graphNodeInputPortMouseArea").length, 2)
        compare(findNamedItems(host, "graphNodeOutputPortMouseArea").length, 2)
        verify(allVisible(findNamedItems(host, "graphNodeInputPortLabel"), false))
        verify(allVisible(findNamedItems(host, "graphNodeOutputPortLabel"), false))
    }

    function test_collapsed_flowchart_keeps_compact_header_title_and_hides_body_surface() {
        var payload = flowchartPayload("decision")
        payload.title = "Flowchart"
        payload.display_name = "Flowchart"
        payload.properties = {
            "title": "Flowchart",
            "body": "Review request routing and approval outcomes."
        }
        payload.collapsed = true
        var host = createHost(payload)
        verify(host !== null)
        tryVerify(function() {
            return findNamedItems(host, "graphNodeSurfaceLoader").length === 1
                && findNamedItems(host, "graphNodeTitle").length === 1
        })
        var loader = findNamedItems(host, "graphNodeSurfaceLoader")[0]
        var titleItem = findNamedItems(host, "graphNodeTitle")[0]
        compare(findNamedItems(host, "graphNodeFlowchartBodyText").length, 0)
        verify(!loader.surfaceLoaded)
        verify(titleItem.visible)
        compare(titleItem.text, "Flowchart")
    }

    function test_flowchart_host_hides_raw_port_labels_and_keeps_port_handles() {
        var payload = flowchartPayload("decision")
        payload.properties.body = "Review the incoming data and choose the next branch."
        var host = createHost(payload)
        verify(host !== null)
        tryVerify(function() {
            return findNamedItems(host, "graphNodeTitle").length === 1
                && findNamedItems(host, "graphNodeFlowchartBodyText").length === 1
                && findNamedItems(host, "graphFlowchartVectorShape").length >= 1
        })
        var titleItem = findNamedItems(host, "graphNodeTitle")[0]
        var bodyText = findNamedItems(host, "graphNodeFlowchartBodyText")[0]
        verify(host.isFlowchartSurface)
        verify(!host._useHostChrome)
        verify(!titleItem.visible)
        compare(bodyText.text, "Review the incoming data and choose the next branch.")
        compare(findNamedItems(host, "graphNodeInputPortDot").length, 2)
        compare(findNamedItems(host, "graphNodeOutputPortDot").length, 2)
        compare(findNamedItems(host, "graphNodeInputPortMouseArea").length, 2)
        compare(findNamedItems(host, "graphNodeOutputPortMouseArea").length, 2)
        verify(allVisible(findNamedItems(host, "graphNodeInputPortLabel"), false))
        verify(allVisible(findNamedItems(host, "graphNodeOutputPortLabel"), false))
    }

    function test_new_flowchart_silhouette_variants_load_on_host_surface() {
        var variants = [
            "card", "callout", "multi_document", "tick", "timestamp",
            "message", "isometric_cube", "cube", "actor", "star", "x"
        ]
        for (var variantIndex = 0; variantIndex < variants.length; ++variantIndex) {
            var variant = variants[variantIndex]
            var payload = flowchartPayload(variant)
            payload.title = variant
            payload.display_name = variant
            payload.properties.title = variant
            var host = createHost(payload)
            verify(host !== null, variant)
            tryVerify(function() {
                return findNamedItems(host, "graphFlowchartSilhouette").length >= 1
                    && findNamedItems(host, "graphFlowchartVectorShape").length >= 1
            })
            var silhouettes = findNamedItems(host, "graphFlowchartSilhouette")
            var vectorShapes = findNamedItems(host, "graphFlowchartVectorShape")
            var visibleSilhouettes = []
            var visibleVectorShapes = []
            for (var silhouetteIndex = 0; silhouetteIndex < silhouettes.length; ++silhouetteIndex) {
                if (visibleWithin(silhouettes[silhouetteIndex], host))
                    visibleSilhouettes.push(silhouettes[silhouetteIndex])
            }
            for (var vectorIndex = 0; vectorIndex < vectorShapes.length; ++vectorIndex) {
                if (visibleWithin(vectorShapes[vectorIndex], host))
                    visibleVectorShapes.push(vectorShapes[vectorIndex])
            }
            verify(visibleSilhouettes.length > 0, variant)
            var silhouette = visibleSilhouettes[0]
            if (variant === "timestamp") {
                compare(visibleVectorShapes.length, 0, variant)
                var previewItems = findNamedItems(host, "graphFlowchartTimestampPreviewText")
                verify(previewItems.length >= 1, variant)
                verify(!previewItems[0].visible, variant)
            } else {
                verify(visibleVectorShapes.length > 0, variant)
            }
            if (variant === "multi_document") {
                var backPages = findNamedItems(host, "graphFlowchartMultiDocumentBackPage")
                var middlePages = findNamedItems(host, "graphFlowchartMultiDocumentMiddlePage")
                var details = findNamedItems(host, "graphFlowchartVectorDetails")
                var visibleBackPage = false
                var visibleMiddlePage = false
                var visibleDetails = false
                for (var backIndex = 0; backIndex < backPages.length; ++backIndex)
                    visibleBackPage = visibleBackPage || visibleWithin(backPages[backIndex], host)
                for (var middleIndex = 0; middleIndex < middlePages.length; ++middleIndex)
                    visibleMiddlePage = visibleMiddlePage || visibleWithin(middlePages[middleIndex], host)
                for (var detailIndex = 0; detailIndex < details.length; ++detailIndex)
                    visibleDetails = visibleDetails || visibleWithin(details[detailIndex], host)
                verify(visibleBackPage, variant)
                verify(visibleMiddlePage, variant)
                verify(details.length > 0, variant)
                verify(!visibleDetails, variant)
            }
            if (variant === "isometric_cube") {
                var detailPath = String(silhouette.detailPathData || "")
                var outlinePath = String(silhouette.outlinePathData || "")
                var topMove = outlinePath.split(" L ", 1)[0]
                verify(topMove.length > 0, variant)
                verify(detailPath.indexOf(topMove) === -1, variant)
            }
        }
    }

    function test_icon_like_flowchart_variants_do_not_fallback_to_library_label() {
        var variants = [
            "card", "callout", "multi_document", "tick", "message",
            "isometric_cube", "cube", "actor", "star", "x"
        ]
        for (var variantIndex = 0; variantIndex < variants.length; ++variantIndex) {
            var variant = variants[variantIndex]
            var payload = flowchartPayload(variant)
            payload.title = variant
            payload.display_name = variant
            payload.properties = {"title": variant, "body": "   "}
            var host = createHost(payload)
            verify(host !== null, variant)
            tryVerify(function() { return findNamedItems(host, "graphNodeFlowchartBodyText").length === 1 })
            compare(String(findNamedItems(host, "graphNodeFlowchartBodyText")[0].text || ""), "", variant)
        }

        var timestampPayload = flowchartPayload("timestamp")
        timestampPayload.title = "Timestamp"
        timestampPayload.display_name = "Timestamp"
        timestampPayload.properties = {
            "title": "Timestamp",
            "body": "%date{ddd mmm dd yyyy HH:MM:ss}%"
        }
        var timestampHost = createHost(timestampPayload)
        verify(timestampHost !== null)
        tryVerify(function() {
            var bodies = findNamedItems(timestampHost, "graphNodeFlowchartBodyText")
            for (var bodyIndex = 0; bodyIndex < bodies.length; ++bodyIndex) {
                if (visibleWithin(bodies[bodyIndex], timestampHost))
                    return true
            }
            return false
        })
        var timestampBodies = findNamedItems(timestampHost, "graphNodeFlowchartBodyText")
        var timestampBody = null
        for (var timestampBodyIndex = 0; timestampBodyIndex < timestampBodies.length; ++timestampBodyIndex) {
            if (visibleWithin(timestampBodies[timestampBodyIndex], timestampHost))
                timestampBody = timestampBodies[timestampBodyIndex]
        }
        verify(timestampBody !== null)
        var timestampText = String(timestampBody.text || "")
        verify(timestampText.length > 0)
        verify(timestampText !== "Timestamp")
        verify(timestampText.indexOf("%date") === -1)
    }

    function test_timestamp_flowchart_surface_actions_commit_live_snapshot_and_manual_values() {
        var payload = flowchartPayload("timestamp")
        payload.node_id = "node_flowchart_visual_polish"
        payload.title = "Timestamp"
        payload.display_name = "Timestamp"
        payload.properties = {
            "title": "Timestamp",
            "body": "%date{ddd mmm dd yyyy HH:MM:ss}%",
            "live": false
        }
        var host = createHost(payload)
        verify(host !== null)
        tryVerify(function() { return findNamedItems(host, "graphNodeFlowchartSurface").length === 1 })
        var surface = findNamedItems(host, "graphNodeFlowchartSurface")[0]
        var actions = surface.surfaceActions
        compare(JSON.stringify(actions.map(function(action) { return action.id })), JSON.stringify([
            "timestamp_toggle_live", "timestamp_update_now", "timestamp_edit_manual"
        ]))
        var actionsById = {}
        for (var actionIndex = 0; actionIndex < actions.length; ++actionIndex)
            actionsById[actions[actionIndex].id] = actions[actionIndex]
        compare(actionsById.timestamp_toggle_live.icon, "keep-live")
        compare(actionsById.timestamp_update_now.icon, "clock-update")
        compare(actionsById.timestamp_edit_manual.icon, "calendar")
        verify(!actionsById.timestamp_toggle_live.checked)
        verify(actionsById.timestamp_update_now.enabled)

        var events = []
        host.inlinePropertyCommitted.connect(function(nodeId, key, value) {
            events.push([String(nodeId), String(key), value])
        })
        verify(surface.dispatchSurfaceAction("timestamp_toggle_live"))
        tryCompare(events, "length", 1)
        compare(events[0][0], "node_flowchart_visual_polish")
        compare(events[0][1], "live")
        compare(events[0][2], true)

        verify(surface.dispatchSurfaceAction("timestamp_update_now"))
        tryCompare(events, "length", 2)
        compare(events[1][1], "body")
        verify(String(events[1][2]).indexOf("%date") === -1)
        compare(String(events[1][2]).split(":").length - 1, 2)

        verify(surface.dispatchSurfaceAction("timestamp_edit_manual"))
        tryVerify(function() { return surface.timestampManualEditorOpen })
        verify(String(surface.timestampManualEditorText || "").indexOf("%date") === -1)
        var manualValue = "Mon Jan 02 2023 03:04:05"
        verify(surface.acceptTimestampManualEdit(manualValue))
        tryVerify(function() { return !surface.timestampManualEditorOpen && events.length === 3 })
        compare(events[2][0], "node_flowchart_visual_polish")
        compare(events[2][1], "body")
        compare(events[2][2], manualValue)
    }

    function test_timestamp_live_property_drives_rendered_body_text() {
        var payload = flowchartPayload("timestamp")
        payload.title = "Timestamp"
        payload.display_name = "Timestamp"
        payload.properties = {
            "title": "Timestamp",
            "body": "Stored snapshot",
            "live": true
        }
        var host = createHost(payload)
        verify(host !== null)
        tryVerify(function() { return findNamedItems(host, "graphNodeFlowchartSurface").length === 1 })
        compare(host.surfaceVariant, "timestamp")
        verify(findNamedItems(host, "graphNodeFlowchartSurface")[0].isTimestampSurface)
        tryVerify(function() {
            var bodies = findNamedItems(host, "graphNodeFlowchartBodyText")
            for (var bodyIndex = 0; bodyIndex < bodies.length; ++bodyIndex) {
                if (visibleWithin(bodies[bodyIndex], host))
                    return true
            }
            return false
        })
        var surface = findNamedItems(host, "graphNodeFlowchartSurface")[0]
        var bodies = findNamedItems(host, "graphNodeFlowchartBodyText")
        var bodyText = null
        for (var bodyIndex = 0; bodyIndex < bodies.length; ++bodyIndex) {
            if (visibleWithin(bodies[bodyIndex], host))
                bodyText = bodies[bodyIndex]
        }
        verify(bodyText !== null)
        surface.timestampNowText = "Sun May 24 2026 17:35:45"
        tryCompare(bodyText, "text", "Sun May 24 2026 17:35:45")
        var actions = surface.surfaceActions
        var actionsById = {}
        for (var actionIndex = 0; actionIndex < actions.length; ++actionIndex)
            actionsById[actions[actionIndex].id] = actions[actionIndex]
        verify(actionsById.timestamp_toggle_live.checked)
        verify(!actionsById.timestamp_update_now.enabled)
    }

    function test_flowchart_body_text_uses_fallback_chain_and_passive_style_hooks() {
        var payload = flowchartPayload("database")
        payload.title = "Archive"
        payload.display_name = "Decision"
        payload.properties = {"title": "Archive", "body": "   "}
        payload.visual_style = {
            "text_color": "#204060",
            "font_size": 17,
            "font_weight": "bold"
        }
        var host = createHost(payload)
        verify(host !== null)
        tryVerify(function() {
            return findNamedItems(host, "graphNodeFlowchartBodyText").length === 1
                && findNamedItems(host, "graphNodeTitle").length === 1
        })
        var bodyText = findNamedItems(host, "graphNodeFlowchartBodyText")[0]
        var titleItem = findNamedItems(host, "graphNodeTitle")[0]
        compare(String(bodyText.text || ""), "Archive")
        verify(!titleItem.visible)
        compare(bodyText.font.pixelSize, 17)
        verify(bodyText.font.bold)
        compare(String(bodyText.color).toLowerCase(), "#204060")
    }

    function test_graph_node_host_loads_shared_planning_card_surface() {
        var payload = passiveSurfacePayload(
            "planning",
            "task_card",
            "Ship parser",
            {
                "title": "Ship parser",
                "body": "Finalize validation and release notes.",
                "owner": "Platform",
                "due_date": "2026-03-31",
                "status": "in_progress"
            },
            248,
            168
        )
        var host = createHost(payload)
        verify(host !== null)
        tryVerify(function() {
            return findNamedItems(host, "graphNodePlanningSurface").length === 1
        }, 1000)
        var loader = findNamedItems(host, "graphNodeSurfaceLoader")[0]
        compare(loader.loadedSurfaceKey, "planning")
        verify(loader.contentHeight > 0)
        compare(findNamedItems(host, "graphNodeInputPortMouseArea").length, 2)
        compare(findNamedItems(host, "graphNodeOutputPortMouseArea").length, 2)
        verify(allVisible(findNamedItems(host, "graphNodeInputPortLabel"), false))
        verify(allVisible(findNamedItems(host, "graphNodeOutputPortLabel"), false))
    }

    function test_graph_node_host_loads_shared_annotation_note_surface() {
        var payload = passiveSurfacePayload(
            "annotation",
            "sticky_note",
            "Release note",
            {
                "title": "Release note",
                "body": "Track follow-up messaging for the rollout."
            },
            228,
            152
        )
        var host = createHost(payload)
        verify(host !== null)
        tryVerify(function() {
            return findNamedItems(host, "graphNodeAnnotationSurface").length === 1
        }, 1000)
        var loader = findNamedItems(host, "graphNodeSurfaceLoader")[0]
        compare(loader.loadedSurfaceKey, "annotation")
        verify(loader.contentHeight > 0)
        compare(findNamedItems(host, "graphNodeInputPortMouseArea").length, 2)
        compare(findNamedItems(host, "graphNodeOutputPortMouseArea").length, 2)
        verify(allVisible(findNamedItems(host, "graphNodeInputPortLabel"), false))
        verify(allVisible(findNamedItems(host, "graphNodeOutputPortLabel"), false))
    }

    function test_graph_node_host_loads_bare_text_annotation_surface() {
        var payload = passiveSurfacePayload(
            "annotation",
            "text",
            "Text",
            {
                "text": "**Markdown** note",
                "format": "markdown",
                "font_size": 20,
                "font_weight": "bold",
                "text_color": "#AABBCC",
                "horizontal_alignment": "center",
                "wrap_mode": "word"
            },
            240,
            96
        )
        payload.type_id = "passive.annotation.text"
        payload.surface_spec = bareTextSurfaceSpec()
        var host = createHost(payload)
        verify(host !== null)
        tryVerify(function() {
            return findNamedItems(host, "graphBareTextSurface").length === 1
                && findNamedItems(host, "graphBareTextRenderedText").length === 1
        }, 1000)
        var loader = findNamedItems(host, "graphNodeSurfaceLoader")[0]
        compare(loader.loadedSurfaceKey, "annotation_text")
        verify(loader.contentHeight > 0)
        compare(findNamedItems(host, "graphNodeInputPortMouseArea").length, 2)
        compare(findNamedItems(host, "graphNodeOutputPortMouseArea").length, 2)
    }

    function test_library_flowchart_visual_fits_multi_document_to_metadata_aspect_ratio() {
        var expectedRatio = 228 / 128
        var visual = createTemporaryObject(
            libraryNodeVisualComponent,
            stage,
            {
                "width": 44,
                "height": 32,
                "displayName": "Multi-Document",
                "fillColor": "#26158bd7",
                "fillCompositeBaseColor": "#ffffffff",
                "libraryVisual": {
                    "kind": "flowchart_shape",
                    "shape_id": "multi_document",
                    "surface_variant": "multi_document",
                    "aspect_ratio": expectedRatio
                }
            }
        )
        verify(visual !== null)
        tryVerify(function() {
            return findNamedItems(visual, "graphFlowchartSilhouette").length === 1
        }, 1000)
        var silhouette = findNamedItems(visual, "graphFlowchartSilhouette")[0]
        verify(Math.abs(silhouette.width - 44) < 0.01)
        verify(Math.abs(silhouette.height - (44 / expectedRatio)) < 0.01)
        verify(Math.abs((silhouette.width / silhouette.height) - expectedRatio) < 0.01)
        verify(silhouette.height < 32)
        verify(Math.abs(silhouette.fillColor.a - 1) < 0.001)
    }

    function test_graph_node_host_loads_group_backdrop_without_body_or_shadow() {
        var host = createHost(groupBackdropPayload({"title": ""}), {"showShadow": true})
        verify(host !== null)
        tryVerify(function() {
            return findNamedItems(host, "graphNodeGroupBackdropSurface").length === 1
        }, 1000)
        var loader = findNamedItems(host, "graphNodeSurfaceLoader")[0]
        var titleText = findNamedItems(host, "graphNodeTitle")[0]
        compare(findNamedItems(host, "graphNodeGroupBackdropBodyText").length, 0)
        compare(findNamedItems(host, "graphGroupBackdropBodyEditor").length, 0)
        compare(findNamedItems(host, "graphNodeGroupBackdropRichTextBlock").length, 0)
        compare(findNamedItems(host, "graphGroupBackdropLivePreviewShadow").length, 0)
        compare(findNamedItems(host, "graphNodeGroupBackdropBadgeDot").length, 0)
        verify(titleText !== null)
        compare(loader.loadedSurfaceKey, "group_backdrop")
        verify(loader.contentHeight > 0)
        verify(!host._useHostChrome)
        verify(!host._backgroundShadowVisible)
        verify(!host._shadowVisible)
        compare(titleText.text, "")
        compare(findNamedItems(host, "graphNodeInputPortMouseArea").length, 2)
        compare(findNamedItems(host, "graphNodeOutputPortMouseArea").length, 2)
    }

    function test_selected_untitled_group_shows_prompt_and_edits_an_empty_title() {
        var canvasProxy = createTemporaryObject(groupCanvasProxyComponent, stage)
        verify(canvasProxy !== null)
        var payload = groupBackdropPayload({"title": ""})
        var primaryHost = createHost(payload, {"canvasItem": canvasProxy})
        var overlayHost = createHost(payload, {
            "canvasItem": canvasProxy,
            "surfaceVariantOverride": "group_backdrop_input_overlay"
        })
        verify(primaryHost !== null)
        verify(overlayHost !== null)
        tryVerify(function() {
            return findNamedItems(primaryHost, "graphNodeTitle").length === 1
                && findNamedItems(overlayHost, "graphNodeTitleEditor").length === 1
        }, 1000)

        var primaryHeader = findNamedItems(primaryHost, "graphNodeHeaderLayer")[0]
        var primaryBackground = findNamedItems(primaryHost, "graphNodeChromeBackgroundLayer")[0]
        var primaryChrome = findNamedItems(primaryHost, "graphNodeChrome")[0]
        var primarySelectedHalo = findNamedItems(primaryHost, "graphNodeSelectedHalo")[0]
        var primaryDisplay = findNamedItems(primaryHost, "graphNodeTitleDisplay")[0]
        var primaryTitle = findNamedItems(primaryHost, "graphNodeTitle")[0]
        var overlayDisplay = findNamedItems(overlayHost, "graphNodeTitleDisplay")[0]
        var overlayTitle = findNamedItems(overlayHost, "graphNodeTitle")[0]
        var overlayEditor = findNamedItems(overlayHost, "graphNodeTitleEditor")[0]
        verify(primaryHost.isSelected)
        verify(!primaryHost._useHostChrome)
        verify(primaryBackground.selectedChromeFreeOutlineOnly)
        verify(!primarySelectedHalo.visible)
        verify(primarySelectedHalo.opacity < 0.01)
        verify(primaryChrome.visible)
        verify(primaryChrome.color.a === 0)
        verify(primaryHeader.primaryGroupBackdropTitleSuppressedByInputOverlay)
        verify(primaryDisplay.visible)
        verify(!primaryTitle.visible)
        compare(primaryTitle.text, "Double click to edit title")
        verify(overlayDisplay.visible)
        compare(overlayTitle.text, "Double click to edit title")

        var titlePoint = overlayTitle.mapToItem(
            overlayHost,
            overlayTitle.width * 0.5,
            overlayTitle.height * 0.5
        )
        verify(overlayHost.requestInlineTitleEditAt(titlePoint.x, titlePoint.y))
        tryCompare(overlayEditor, "visible", true, 1000)
        verify(primaryDisplay.visible)
        verify(!primaryTitle.visible)
        compare(overlayEditor.text, "")
    }

    function test_collapsed_group_backdrop_ignores_node_icon_source_for_title_contract() {
        var payload = groupBackdropPayload({"title": "Named Group"})
        payload.title = "Named Group"
        payload.collapsed = true
        payload.icon_source = Qt.resolvedUrl(
            "../../ea_node_editor/assets/app_icon/corex_app_minimal.svg"
        )
        var host = createHost(payload, {"graphLabelPixelSize": 16})
        verify(host !== null)
        tryVerify(function() {
            return findNamedItems(host, "graphNodeGroupTitleIcon").length === 1
        }, 1000)
        var titleText = findNamedItems(host, "graphNodeTitle")[0]
        var titleIcon = findNamedItems(host, "graphNodeTitleIcon")[0]
        var groupIcon = findNamedItems(host, "graphNodeGroupTitleIcon")[0]
        verify(titleText !== null)
        verify(titleIcon !== null)
        verify(groupIcon !== null)
        verify(!titleIcon.visible)
        compare(groupIcon.width, 16)
        compare(groupIcon.height, 16)
        compare(titleText.text, "Named Group")
    }

    function test_collapsed_group_backdrop_width_fits_long_title_with_stale_metrics() {
        var title = "Tabular Plot Showcase Direct"
        var payload = groupBackdropPayload({"title": title})
        payload.title = title
        payload.collapsed = true
        payload.surface_metrics = {"collapsed_width": 130}
        var host = createHost(payload)
        verify(host !== null)
        tryVerify(function() {
            return findNamedItems(host, "graphNodeTitleDisplay").length === 1
                && host.width > 130
        }, 1000)
        var titleText = findNamedItems(host, "graphNodeTitle")[0]
        compare(titleText.text, title)
        verify(host.width > 130)
        verify(host.width < 420)
        verify(!titleText.truncated)
    }
}
