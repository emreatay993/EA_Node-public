from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ea_node_editor.graph.model import GraphModel
from ea_node_editor.graph.hierarchy import scope_edges
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.ui_qml.graph_scene.context import _GraphSceneContext
from ea_node_editor.ui_qml.graph_scene.payload_cache_sync import ScenePayloadCacheSync
from ea_node_editor.ui_qml.graph_scene.state_support import _GraphScenePayloadCache
from ea_node_editor.ui_qml.graph_scene_scope_selection import GraphSceneScopeSelection
from ea_node_editor.ui_qml.graph_scene_payload import GraphScenePayloadBuilder
from ea_node_editor.ui_qml.graph_scene_payload.backdrop_partitioner import _GraphSceneBackdropPartitioner

_EXPECTED_GRAPHICS_PAYLOAD_FACTS = {
    "show_port_labels": False,
    "graph_label_pixel_size": 16,
    "graph_node_icon_pixel_size": 12,
    "lightweight_canvas": True,
}


def _edge_payload(
    edge_id: str,
    source_node_id: str,
    source_port_key: str,
    target_node_id: str,
    target_port_key: str,
) -> dict:
    return {
        "edge_id": edge_id,
        "source_node_id": source_node_id,
        "source_port_key": source_port_key,
        "target_node_id": target_node_id,
        "target_port_key": target_port_key,
    }


def _edge_indexes(cache: _GraphScenePayloadCache) -> dict:
    return {
        "edge_payload_by_id": dict(cache.edge_payload_by_id),
        "edge_index_by_id": dict(cache.edge_index_by_id),
        "edge_order": list(cache.edge_order),
        "incident_edge_ids_by_node_id": {
            node_id: set(edge_ids)
            for node_id, edge_ids in cache.incident_edge_ids_by_node_id.items()
        },
        "edge_ids_by_pair": {
            pair: set(edge_ids)
            for pair, edge_ids in cache.edge_ids_by_pair.items()
        },
        "edge_ids_by_source_port": {
            port: set(edge_ids)
            for port, edge_ids in cache.edge_ids_by_source_port.items()
        },
        "edge_ids_by_target_port": {
            port: set(edge_ids)
            for port, edge_ids in cache.edge_ids_by_target_port.items()
        },
    }


def _node_indexes(cache: _GraphScenePayloadCache) -> dict:
    return {
        "node_payload_location_by_id": dict(cache.node_payload_location_by_id),
        "minimap_node_index_by_id": dict(cache.minimap_node_index_by_id),
    }


class _FakePayloadBuilder:
    def __init__(self) -> None:
        self.node_payload = {
            "node_id": "n1",
            "x": 10.0,
            "y": 12.0,
            "title": "updated",
            "ports": [{"key": "payload"}],
        }
        self.minimap_payload = {"node_id": "n1", "x": 10.0, "y": 12.0}
        self.connection_update = {
            "ports": [{"key": "result"}],
            "inline_properties": [{"key": "status", "value": "ready"}],
        }
        self.last_build_node_kwargs = {}
        self.last_build_connection_kwargs = {}

    def build_node_payloads_for_ids(self, **kwargs):
        self.last_build_node_kwargs = dict(kwargs)
        return (
            [self.node_payload],
            [],
            [self.minimap_payload],
        )

    def build_node_connection_payloads_for_ids(self, **kwargs):
        self.last_build_connection_kwargs = dict(kwargs)
        return {"n1": self.connection_update}


class _FakeContext:
    def __init__(
        self,
        cache: _GraphScenePayloadCache,
        workspace: SimpleNamespace,
        payload_builder: _FakePayloadBuilder | None = None,
    ) -> None:
        self._bridge = SimpleNamespace(_payload_cache=cache)
        self._workspace = workspace
        self._payload_builder = payload_builder or _FakePayloadBuilder()
        self.model = SimpleNamespace()
        self.registry = SimpleNamespace()
        self.workspace_id = "ws"
        self.scope_path = ()
        self.graph_theme_bridge = None
        self.graphics_show_port_labels = False
        self.graphics_graph_label_pixel_size = 16
        self.graphics_node_title_icon_pixel_size = 12
        self.graphics_lightweight_canvas = True
        self.mutation_counters: list[tuple[str, int, str]] = []

    def workspace_or_none(self):
        return self._workspace

    @staticmethod
    def _validated_comment_peek_node_id() -> str:
        return ""

    @staticmethod
    def _normalized_id_set(values) -> set[str]:
        return {
            normalized
            for value in values
            if (normalized := str(value or "").strip())
        }

    @staticmethod
    def _edge_payload_id(payload: dict) -> str:
        return str(payload.get("edge_id", "") or "").strip()

    def record_mutation_counter(self, counter_name: str, amount: int = 1, *, reason: str = "") -> None:
        self.mutation_counters.append((counter_name, amount, reason))


class GraphScenePayloadCacheSyncTests(unittest.TestCase):
    def assert_edge_indexes_match_fresh_rebuild(self, cache: _GraphScenePayloadCache) -> None:
        expected = _GraphScenePayloadCache(edges=list(cache.edges))
        expected.rebuild_indexes()
        self.assertEqual(_edge_indexes(cache), _edge_indexes(expected))

    def test_edge_only_reindex_matches_full_rebuild_for_same_id_endpoint_change(self) -> None:
        cache = _GraphScenePayloadCache(
            nodes=[{"node_id": "n1"}, {"node_id": "n2"}, {"node_id": "n3"}],
            minimap_nodes=[{"node_id": "n1"}, {"node_id": "n2"}, {"node_id": "n3"}],
            edges=[
                _edge_payload("e1", "n1", "out", "n2", "in"),
                _edge_payload("e2", "n2", "out", "n3", "in"),
            ],
        )
        cache.rebuild_indexes()
        node_indexes_before = _node_indexes(cache)
        full_rebuild_count_before = cache.rebuild_index_call_count

        cache.edges[0] = _edge_payload("e1", "n3", "alt_out", "n1", "alt_in")
        cache.reindex_edges_only()

        expected = _GraphScenePayloadCache(
            nodes=list(cache.nodes),
            minimap_nodes=list(cache.minimap_nodes),
            edges=list(cache.edges),
        )
        expected.rebuild_indexes()

        self.assertEqual(_edge_indexes(cache), _edge_indexes(expected))
        self.assertEqual(_node_indexes(cache), node_indexes_before)
        self.assertEqual(cache.rebuild_index_call_count, full_rebuild_count_before)
        self.assertEqual(cache.edge_only_reindex_call_count, 1)

    def test_port_connection_counts_for_nodes_match_scope_edge_counts(self) -> None:
        edge_payloads = [
            _edge_payload("e1", "n1", "out", "n2", "in"),
            _edge_payload("e2", "n3", "out", "n1", "in"),
            _edge_payload("e3", "n1", "loop_out", "n1", "loop_in"),
            _edge_payload("e4", "n2", "out", "n3", "in"),
        ]
        cache = _GraphScenePayloadCache(
            nodes=[{"node_id": "n1"}, {"node_id": "n2"}, {"node_id": "n3"}],
            minimap_nodes=[{"node_id": "n1"}, {"node_id": "n2"}, {"node_id": "n3"}],
            edges=edge_payloads,
        )
        cache.rebuild_indexes()

        requested = {"n1", "n2"}
        full_counts = _GraphSceneBackdropPartitioner.port_connection_counts(
            [SimpleNamespace(**payload) for payload in edge_payloads]
        )
        expected = {
            key: count
            for key, count in full_counts.items()
            if key[0] in requested
        }

        self.assertEqual(cache.port_connection_counts_for_nodes(requested), expected)
        self.assertEqual(cache.port_connection_counts_for_nodes({"missing"}), {})

    def test_position_replacement_preserves_existing_indexes(self) -> None:
        workspace = SimpleNamespace(nodes={"n1": SimpleNamespace(x=42.0, y=84.0)}, edges={})
        original_payload = {"node_id": "n1", "x": 0.0, "y": 0.0}
        cache = _GraphScenePayloadCache(
            nodes=[original_payload],
            minimap_nodes=[{"node_id": "n1", "x": 0.0, "y": 0.0}],
            edges=[_edge_payload("e1", "n1", "out", "n2", "in")],
        )
        cache.rebuild_indexes()
        node_indexes_before = _node_indexes(cache)
        edge_indexes_before = _edge_indexes(cache)
        full_rebuild_count_before = cache.rebuild_index_call_count

        sync = ScenePayloadCacheSync(_FakeContext(cache, workspace))
        node_payloads, minimap_payloads = sync.replace_cached_node_position_payloads({"n1"})

        self.assertEqual(node_payloads[0]["x"], 42.0)
        self.assertEqual(node_payloads[0]["y"], 84.0)
        self.assertEqual(minimap_payloads[0]["x"], 42.0)
        self.assertEqual(minimap_payloads[0]["y"], 84.0)
        self.assertIs(cache.nodes[0], node_payloads[0])
        self.assertIsNot(cache.nodes[0], original_payload)
        self.assertEqual(_node_indexes(cache), node_indexes_before)
        self.assertEqual(_edge_indexes(cache), edge_indexes_before)
        self.assertEqual(cache.rebuild_index_call_count, full_rebuild_count_before)

    def test_full_node_replacement_preserves_existing_indexes(self) -> None:
        workspace = SimpleNamespace(nodes={"n1": SimpleNamespace(x=10.0, y=12.0)}, edges={})
        payload_builder = _FakePayloadBuilder()
        cache = _GraphScenePayloadCache(
            nodes=[{"node_id": "n1", "x": 0.0, "y": 0.0, "title": "old"}],
            minimap_nodes=[{"node_id": "n1", "x": 0.0, "y": 0.0}],
            edges=[_edge_payload("e1", "n1", "out", "n2", "in")],
        )
        cache.rebuild_indexes()
        node_indexes_before = _node_indexes(cache)
        edge_indexes_before = _edge_indexes(cache)
        full_rebuild_count_before = cache.rebuild_index_call_count
        previous_payload = cache.nodes[0]

        sync = ScenePayloadCacheSync(_FakeContext(cache, workspace, payload_builder=payload_builder))
        replacement = sync.replace_cached_full_node_payloads(
            {"n1"},
            changed_fields_by_node_id={"n1": {"node.title"}},
        )

        self.assertIsNotNone(replacement)
        self.assertIs(payload_builder.last_build_node_kwargs["previous_payloads_by_id"]["n1"], previous_payload)
        self.assertEqual(
            payload_builder.last_build_node_kwargs["changed_fields_by_node_id"],
            {"n1": {"node.title"}},
        )
        self.assertEqual(
            {
                name: payload_builder.last_build_node_kwargs[name]
                for name in _EXPECTED_GRAPHICS_PAYLOAD_FACTS
            },
            _EXPECTED_GRAPHICS_PAYLOAD_FACTS,
        )
        self.assertEqual(cache.nodes[0]["title"], "updated")
        self.assertIs(cache.nodes[0], payload_builder.node_payload)
        self.assertIs(cache.minimap_nodes[0], payload_builder.minimap_payload)
        self.assertEqual(_node_indexes(cache), node_indexes_before)
        self.assertEqual(_edge_indexes(cache), edge_indexes_before)
        self.assertEqual(cache.rebuild_index_call_count, full_rebuild_count_before)

    def test_connection_payload_replacement_swaps_dict_and_copies_updated_nested_fields(self) -> None:
        workspace = SimpleNamespace(nodes={"n1": SimpleNamespace(x=10.0, y=12.0)}, edges={})
        payload_builder = _FakePayloadBuilder()
        original_ports = [{"key": "old"}]
        original_inline = [{"key": "status", "value": "old"}]
        original_payload = {
            "node_id": "n1",
            "ports": original_ports,
            "inline_properties": original_inline,
            "properties": {"title": "Original"},
        }
        cache = _GraphScenePayloadCache(
            nodes=[original_payload],
            minimap_nodes=[{"node_id": "n1"}],
            edges=[],
        )
        cache.rebuild_indexes()

        sync = ScenePayloadCacheSync(_FakeContext(cache, workspace, payload_builder=payload_builder))
        updated_payloads = sync.replace_cached_connection_node_payloads({"n1"})

        self.assertEqual(len(updated_payloads), 1)
        self.assertIs(cache.nodes[0], updated_payloads[0])
        self.assertIsNot(cache.nodes[0], original_payload)
        self.assertEqual(original_payload["ports"], original_ports)
        self.assertEqual(original_payload["inline_properties"], original_inline)
        self.assertEqual(cache.nodes[0]["ports"], [{"key": "result"}])
        self.assertIsNot(cache.nodes[0]["ports"], payload_builder.connection_update["ports"])
        self.assertIsNot(cache.nodes[0]["inline_properties"], payload_builder.connection_update["inline_properties"])
        self.assertEqual(
            {
                name: payload_builder.last_build_connection_kwargs[name]
                for name in _EXPECTED_GRAPHICS_PAYLOAD_FACTS
            },
            _EXPECTED_GRAPHICS_PAYLOAD_FACTS,
        )

    def test_targeted_node_payload_replacement_rebuilds_current_port_projection(self) -> None:
        node = SimpleNamespace(title="Renamed", properties={"title": "Renamed"}, links=[], comments=[])
        workspace = SimpleNamespace(nodes={"n1": node}, edges={})
        original_payload = {
            "node_id": "n1",
            "title": "Old",
            "properties": {"title": "Old"},
            "inline_properties": [{"key": "title", "value": "Old"}],
            "links": [{"label": "old"}],
            "ports": [{"key": "old", "modifiers": [], "principal": False}],
        }
        cache = _GraphScenePayloadCache(
            nodes=[original_payload],
            minimap_nodes=[{"node_id": "n1"}],
            edges=[],
        )
        cache.rebuild_indexes()
        payload_builder = _FakePayloadBuilder()
        payload_builder.node_payload = {
            "node_id": "n1",
            "title": "Renamed",
            "properties": {"title": "Renamed"},
            "inline_properties": [{"key": "title", "value": "Renamed"}],
            "links": [],
            "ports": [
                {
                    "key": "output_2",
                    "data_access": "tree",
                    "modifiers": ["graft"],
                    "principal": True,
                }
            ],
        }

        sync = ScenePayloadCacheSync(
            _FakeContext(cache, workspace, payload_builder=payload_builder)
        )
        updated_payloads = sync.replace_cached_node_payload("n1", node)

        self.assertEqual(len(updated_payloads), 1)
        self.assertIs(cache.nodes[0], updated_payloads[0])
        self.assertIsNot(cache.nodes[0], original_payload)
        self.assertEqual(
            original_payload["ports"],
            [{"key": "old", "modifiers": [], "principal": False}],
        )
        self.assertEqual(cache.nodes[0]["ports"], payload_builder.node_payload["ports"])
        self.assertEqual(cache.nodes[0]["properties"], {"title": "Renamed"})
        self.assertIs(cache.minimap_nodes[0], payload_builder.minimap_payload)
        self.assertEqual(payload_builder.last_build_node_kwargs["node_ids"], {"n1"})
        self.assertIs(
            payload_builder.last_build_node_kwargs["previous_payloads_by_id"]["n1"],
            original_payload,
        )

    def test_node_delta_payload_reuses_replaced_payload_dicts_at_boundary(self) -> None:
        state_bridge = SimpleNamespace(node_delta_payload={})
        cache = _GraphScenePayloadCache(nodes=[], backdrop_nodes=[], minimap_nodes=[], edges=[])
        bridge = SimpleNamespace(state_bridge=state_bridge, _payload_cache=cache)
        context = _GraphSceneContext(bridge, GraphScenePayloadBuilder())
        node_payload = {"node_id": "n1", "ports": [{"key": "payload"}]}

        context._set_node_delta_payload(reason="unit", node_payloads=[node_payload])

        self.assertIs(state_bridge.node_delta_payload["nodes"][0], node_payload)
        self.assertEqual(state_bridge.node_delta_payload["backdrop_nodes"], [])

    def test_added_node_builder_uses_lean_minimap_payload(self) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace = model.active_workspace
        node = model.add_node(workspace.workspace_id, "core.logger", "Logger", 10.0, 20.0)

        nodes_payload, backdrop_payload, minimap_payload = GraphScenePayloadBuilder().build_added_node_payloads_for_ids(
            model=model,
            registry=registry,
            workspace_id=workspace.workspace_id,
            scope_path=(),
            node_ids={node.node_id},
            graph_theme_bridge=None,
        )

        self.assertEqual(len(nodes_payload), 1)
        self.assertEqual(backdrop_payload, [])
        self.assertEqual(len(minimap_payload), 1)
        self.assertIsNot(minimap_payload[0], nodes_payload[0])
        self.assertEqual(set(minimap_payload[0]), {"node_id", "x", "y", "width", "height"})
        self.assertNotIn("ports", minimap_payload[0])
        self.assertNotIn("properties", minimap_payload[0])

    def test_added_node_builder_checks_requested_scope_without_copying_workspace_nodes(self) -> None:
        class _LookupOnlyNodeMap(dict):
            def __iter__(self):
                raise AssertionError("the single-node builder must not enumerate all workspace nodes")

            def keys(self):
                raise AssertionError("the single-node builder must not copy all workspace nodes")

        registry = build_default_registry()
        model = GraphModel()
        workspace = model.active_workspace
        parent = model.add_node(workspace.workspace_id, "core.constant", "Constant", 0.0, 0.0)
        child = model.add_node(workspace.workspace_id, "core.logger", "Logger", 120.0, 60.0)
        child.parent_node_id = parent.node_id
        workspace.nodes = _LookupOnlyNodeMap(workspace.nodes)
        builder = GraphScenePayloadBuilder()

        with patch(
            "ea_node_editor.ui_qml.graph_scene_payload.builder.scope_node_ids",
            side_effect=AssertionError("requested-id publication must not build the full scope list"),
        ):
            root_payloads, _, _ = builder.build_added_node_payloads_for_ids(
                model=model,
                registry=registry,
                workspace_id=workspace.workspace_id,
                scope_path=(),
                node_ids={parent.node_id, child.node_id},
                graph_theme_bridge=None,
                port_connection_counts={},
            )
            child_payloads, _, _ = builder.build_added_node_payloads_for_ids(
                model=model,
                registry=registry,
                workspace_id=workspace.workspace_id,
                scope_path=(parent.node_id,),
                node_ids={parent.node_id, child.node_id},
                graph_theme_bridge=None,
                port_connection_counts={},
            )

        self.assertEqual([payload["node_id"] for payload in root_payloads], [parent.node_id])
        self.assertEqual([payload["node_id"] for payload in child_payloads], [child.node_id])

    def test_selection_checks_only_requested_node_scope_without_building_visible_scope_list(self) -> None:
        model = GraphModel()
        workspace = model.active_workspace
        parent = model.add_node(workspace.workspace_id, "core.constant", "Constant", 0.0, 0.0)
        child = model.add_node(workspace.workspace_id, "core.logger", "Logger", 120.0, 60.0)
        child.parent_node_id = parent.node_id
        emitted_primary_ids: list[str] = []
        context = SimpleNamespace(
            workspace_id=workspace.workspace_id,
            scope_path=(),
            selected_node_ids=[],
            selected_node_lookup={},
            comment_peek_node_id="",
            workspace_or_none=lambda: workspace,
            emit_selection_changed=emitted_primary_ids.append,
        )
        selection = GraphSceneScopeSelection(context)

        with patch(
            "ea_node_editor.ui_qml.graph_scene_scope_selection.scope_node_ids",
            side_effect=AssertionError("selection must validate only the requested ids"),
        ):
            root_selection = selection.normalized_selected_node_ids(
                workspace,
                [child.node_id, parent.node_id, parent.node_id],
            )
            context.scope_path = (parent.node_id,)
            child_selection = selection.normalized_selected_node_ids(
                workspace,
                [parent.node_id, child.node_id],
            )
            selection_changed = selection.set_selected_node_ids(
                [child.node_id, child.node_id],
                workspace=workspace,
            )

        self.assertEqual(root_selection, [parent.node_id])
        self.assertEqual(child_selection, [child.node_id])
        self.assertTrue(selection_changed)
        self.assertEqual(context.selected_node_ids, [child.node_id])
        self.assertEqual(emitted_primary_ids, [child.node_id])

    def test_targeted_node_builder_accepts_precomputed_port_counts(self) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace = model.active_workspace
        source = model.add_node(workspace.workspace_id, "core.constant", "Constant", 0.0, 0.0)
        logger = model.add_node(workspace.workspace_id, "core.logger", "Logger", 240.0, 0.0)
        model.add_edge(workspace.workspace_id, source.node_id, "as_text", logger.node_id, "message")
        builder = GraphScenePayloadBuilder()
        requested = {logger.node_id}
        expected_counts = _GraphSceneBackdropPartitioner.port_connection_counts(scope_edges(workspace, ()))

        default_payloads = builder.build_node_payloads_for_ids(
            model=model,
            registry=registry,
            workspace_id=workspace.workspace_id,
            scope_path=(),
            node_ids=requested,
            graph_theme_bridge=None,
        )
        precomputed_payloads = builder.build_node_payloads_for_ids(
            model=model,
            registry=registry,
            workspace_id=workspace.workspace_id,
            scope_path=(),
            node_ids=requested,
            graph_theme_bridge=None,
            port_connection_counts={
                key: count
                for key, count in expected_counts.items()
                if key[0] in requested
            },
        )

        self.assertEqual(precomputed_payloads, default_payloads)

    def test_edge_replacement_reuses_valid_slot_without_reindex(self) -> None:
        workspace = SimpleNamespace(
            nodes={},
            edges={"e1": SimpleNamespace(edge_id="e1"), "e2": SimpleNamespace(edge_id="e2")},
        )
        cache = _GraphScenePayloadCache(
            nodes=[{"node_id": "n1"}, {"node_id": "n2"}, {"node_id": "n3"}],
            minimap_nodes=[{"node_id": "n1"}, {"node_id": "n2"}, {"node_id": "n3"}],
            edges=[
                _edge_payload("e1", "n1", "out", "n2", "in"),
                _edge_payload("e2", "n2", "out", "n3", "in"),
            ],
        )
        cache.rebuild_indexes()
        node_indexes_before = _node_indexes(cache)
        full_rebuild_count_before = cache.rebuild_index_call_count

        context = _FakeContext(cache, workspace)
        sync = ScenePayloadCacheSync(context)
        updated_payloads = sync.replace_cached_edge_payloads({"e1"}, set(), reuse_existing_payloads=True)

        expected = _GraphScenePayloadCache(
            nodes=list(cache.nodes),
            minimap_nodes=list(cache.minimap_nodes),
            edges=list(cache.edges),
        )
        expected.rebuild_indexes()

        self.assertEqual([payload["edge_id"] for payload in updated_payloads], ["e1"])
        self.assertEqual(_edge_indexes(cache), _edge_indexes(expected))
        self.assertEqual(_node_indexes(cache), node_indexes_before)
        self.assertEqual(cache.rebuild_index_call_count, full_rebuild_count_before)
        self.assertEqual(cache.edge_only_reindex_call_count, 0)
        self.assertEqual(context.mutation_counters, [("cached_edge_payload_in_place", 1, "")])

    def test_style_label_and_geometry_edge_replacement_preserves_routing_indexes(self) -> None:
        original = {
            **_edge_payload("e1", "n1", "out", "n2", "in"),
            "label": "Before",
            "visual_style": {"color": "red"},
            "source_anchor": {"x": 10.0, "y": 20.0},
        }
        replacement = {
            **original,
            "label": "After",
            "visual_style": {"color": "blue"},
            "source_anchor": {"x": 30.0, "y": 40.0},
        }
        workspace = SimpleNamespace(nodes={}, edges={"e1": SimpleNamespace(edge_id="e1")})
        cache = _GraphScenePayloadCache(edges=[original])
        cache.rebuild_indexes()
        context = _FakeContext(cache, workspace)
        sync = ScenePayloadCacheSync(context)
        edge_index_before = dict(cache.edge_index_by_id)
        edge_order_before = list(cache.edge_order)
        incident_before = {key: set(value) for key, value in cache.incident_edge_ids_by_node_id.items()}
        pair_before = {key: set(value) for key, value in cache.edge_ids_by_pair.items()}
        source_before = {key: set(value) for key, value in cache.edge_ids_by_source_port.items()}
        target_before = {key: set(value) for key, value in cache.edge_ids_by_target_port.items()}

        with patch.object(sync, "build_cached_edge_payloads_for_ids", return_value=[replacement]):
            updated_payloads = sync.replace_cached_edge_payloads({"e1"}, set())

        self.assertEqual(updated_payloads, [replacement])
        self.assertIs(cache.edges[0], replacement)
        self.assertIs(cache.edge_payload_by_id["e1"], replacement)
        self.assertEqual(cache.edge_index_by_id, edge_index_before)
        self.assertEqual(cache.edge_order, edge_order_before)
        self.assertEqual(cache.incident_edge_ids_by_node_id, incident_before)
        self.assertEqual(cache.edge_ids_by_pair, pair_before)
        self.assertEqual(cache.edge_ids_by_source_port, source_before)
        self.assertEqual(cache.edge_ids_by_target_port, target_before)
        self.assertEqual(cache.edge_only_reindex_call_count, 0)
        self.assertEqual(context.mutation_counters, [("cached_edge_payload_in_place", 1, "")])

    def test_endpoint_change_falls_back_to_edge_reindex(self) -> None:
        original = _edge_payload("e1", "n1", "out", "n2", "in")
        replacement = _edge_payload("e1", "n1", "out", "n3", "alternate_in")
        workspace = SimpleNamespace(nodes={}, edges={"e1": SimpleNamespace(edge_id="e1")})
        cache = _GraphScenePayloadCache(edges=[original])
        cache.rebuild_indexes()
        context = _FakeContext(cache, workspace)
        sync = ScenePayloadCacheSync(context)

        with patch.object(sync, "build_cached_edge_payloads_for_ids", return_value=[replacement]):
            updated_payloads = sync.replace_cached_edge_payloads({"e1"}, set())

        self.assertEqual(updated_payloads, [replacement])
        self.assertEqual(cache.edge_only_reindex_call_count, 1)
        self.assertEqual(cache.edge_ids_by_target_port, {("n3", "alternate_in"): {"e1"}})
        self.assertIn(
            ("cached_edge_payload_in_place_fallback", 1, "endpoint_change"),
            context.mutation_counters,
        )

    def test_partial_edge_result_falls_back_to_edge_reindex(self) -> None:
        first = _edge_payload("e1", "n1", "out", "n2", "in")
        second = _edge_payload("e2", "n2", "out", "n3", "in")
        replacement = {**first, "label": "updated"}
        workspace = SimpleNamespace(
            nodes={},
            edges={"e1": SimpleNamespace(edge_id="e1"), "e2": SimpleNamespace(edge_id="e2")},
        )
        cache = _GraphScenePayloadCache(edges=[first, second])
        cache.rebuild_indexes()
        context = _FakeContext(cache, workspace)
        sync = ScenePayloadCacheSync(context)

        with patch.object(sync, "build_cached_edge_payloads_for_ids", return_value=[replacement]):
            sync.replace_cached_edge_payloads({"e1", "e2"}, set())

        self.assertEqual(cache.edge_only_reindex_call_count, 1)
        self.assertEqual(cache.edge_order, ["e1"])
        self.assertIn(
            ("cached_edge_payload_in_place_fallback", 1, "partial_result"),
            context.mutation_counters,
        )

    def test_added_edge_without_cache_slot_appends_without_reindex(self) -> None:
        first = _edge_payload("e1", "n1", "out", "n2", "in")
        added = _edge_payload("e2", "n2", "out", "n3", "in")
        workspace = SimpleNamespace(
            nodes={},
            edges={"e1": SimpleNamespace(edge_id="e1"), "e2": SimpleNamespace(edge_id="e2")},
        )
        cache = _GraphScenePayloadCache(edges=[first])
        cache.rebuild_indexes()
        context = _FakeContext(cache, workspace)
        sync = ScenePayloadCacheSync(context)

        with patch.object(sync, "build_cached_edge_payloads_for_ids", return_value=[added]):
            sync.replace_cached_edge_payloads({"e2"}, set())

        self.assertEqual(cache.edge_only_reindex_call_count, 0)
        self.assertEqual(cache.edge_order, ["e1", "e2"])
        self.assert_edge_indexes_match_fresh_rebuild(cache)
        self.assertEqual(
            context.mutation_counters,
            [("cached_edge_payload_structural_incremental", 1, "added_edge")],
        )

    def test_removed_edge_shifts_following_indexes_without_reindex(self) -> None:
        first = _edge_payload("e1", "n1", "out", "n2", "in")
        second = _edge_payload("e2", "n2", "out", "n3", "in")
        workspace = SimpleNamespace(nodes={}, edges={"e2": SimpleNamespace(edge_id="e2")})
        cache = _GraphScenePayloadCache(edges=[first, second])
        cache.rebuild_indexes()
        context = _FakeContext(cache, workspace)
        sync = ScenePayloadCacheSync(context)

        sync.replace_cached_edge_payloads(set(), {"e1"})

        self.assertEqual(cache.edge_only_reindex_call_count, 0)
        self.assertEqual(cache.edge_order, ["e2"])
        self.assert_edge_indexes_match_fresh_rebuild(cache)
        self.assertEqual(
            context.mutation_counters,
            [("cached_edge_payload_structural_incremental", 1, "removed_edge")],
        )

    def test_added_edge_inserts_at_canonical_middle_slot_without_reindex(self) -> None:
        first = _edge_payload("e1", "n1", "out", "n2", "in")
        added = _edge_payload("e2", "n2", "out", "n3", "in")
        third = _edge_payload("e3", "n3", "out", "n4", "in")
        workspace = SimpleNamespace(
            nodes={},
            edges={edge_id: SimpleNamespace(edge_id=edge_id) for edge_id in ("e1", "e2", "e3")},
        )
        cache = _GraphScenePayloadCache(edges=[first, third])
        cache.rebuild_indexes()
        context = _FakeContext(cache, workspace)
        sync = ScenePayloadCacheSync(context)

        with patch.object(sync, "build_cached_edge_payloads_for_ids", return_value=[added]):
            sync.replace_cached_edge_payloads({"e2"}, set())

        self.assertEqual(cache.edge_order, ["e1", "e2", "e3"])
        self.assertEqual(cache.edge_only_reindex_call_count, 0)
        self.assert_edge_indexes_match_fresh_rebuild(cache)

    def test_removed_tail_edge_updates_all_indexes_without_reindex(self) -> None:
        first = _edge_payload("e1", "n1", "out", "n2", "in")
        second = _edge_payload("e2", "n2", "out", "n3", "in")
        workspace = SimpleNamespace(nodes={}, edges={"e1": SimpleNamespace(edge_id="e1")})
        cache = _GraphScenePayloadCache(edges=[first, second])
        cache.rebuild_indexes()
        context = _FakeContext(cache, workspace)

        ScenePayloadCacheSync(context).replace_cached_edge_payloads(set(), {"e2"})

        self.assertEqual(cache.edge_order, ["e1"])
        self.assertEqual(cache.edge_only_reindex_call_count, 0)
        self.assert_edge_indexes_match_fresh_rebuild(cache)

    def test_removed_self_loop_prunes_duplicate_incident_index_key(self) -> None:
        loop = _edge_payload("e1", "n1", "loop_out", "n1", "loop_in")
        workspace = SimpleNamespace(nodes={}, edges={})
        cache = _GraphScenePayloadCache(edges=[loop])
        cache.rebuild_indexes()
        context = _FakeContext(cache, workspace)

        ScenePayloadCacheSync(context).replace_cached_edge_payloads(set(), {"e1"})

        self.assertNotIn("n1", cache.incident_edge_ids_by_node_id)
        self.assert_edge_indexes_match_fresh_rebuild(cache)

    def test_parallel_lane_siblings_replace_in_place_around_add_and_remove(self) -> None:
        first = {**_edge_payload("e1", "n1", "out", "n2", "in"), "pair_lane": -12.0}
        third = {**_edge_payload("e3", "n1", "out", "n2", "in"), "pair_lane": 12.0}
        cache = _GraphScenePayloadCache(edges=[first, third])
        cache.rebuild_indexes()
        workspace = SimpleNamespace(
            nodes={},
            edges={edge_id: SimpleNamespace(edge_id=edge_id) for edge_id in ("e1", "e2", "e3")},
        )
        context = _FakeContext(cache, workspace)
        sync = ScenePayloadCacheSync(context)
        added_payloads = [
            {**first, "pair_lane": -24.0},
            {**_edge_payload("e2", "n1", "out", "n2", "in"), "pair_lane": 0.0},
            {**third, "pair_lane": 24.0},
        ]

        with patch.object(sync, "build_cached_edge_payloads_for_ids", return_value=added_payloads):
            sync.replace_cached_edge_payloads({"e1", "e2", "e3"}, set())

        self.assertEqual([payload["pair_lane"] for payload in cache.edges], [-24.0, 0.0, 24.0])
        self.assert_edge_indexes_match_fresh_rebuild(cache)

        workspace.edges.pop("e2")
        removed_payloads = [{**first, "pair_lane": -12.0}, {**third, "pair_lane": 12.0}]
        with patch.object(sync, "build_cached_edge_payloads_for_ids", return_value=removed_payloads):
            sync.replace_cached_edge_payloads({"e1", "e3"}, {"e2"})

        self.assertEqual([payload["pair_lane"] for payload in cache.edges], [-12.0, 12.0])
        self.assertEqual(cache.edge_only_reindex_call_count, 0)
        self.assert_edge_indexes_match_fresh_rebuild(cache)

    def test_bulk_and_simultaneous_structural_changes_keep_reindex_fallback(self) -> None:
        first = _edge_payload("e1", "n1", "out", "n2", "in")
        second = _edge_payload("e2", "n2", "out", "n3", "in")
        third = _edge_payload("e3", "n3", "out", "n4", "in")

        with self.subTest("bulk add"):
            workspace = SimpleNamespace(
                nodes={},
                edges={edge_id: SimpleNamespace(edge_id=edge_id) for edge_id in ("e1", "e2", "e3")},
            )
            cache = _GraphScenePayloadCache(edges=[first])
            cache.rebuild_indexes()
            context = _FakeContext(cache, workspace)
            sync = ScenePayloadCacheSync(context)
            with patch.object(sync, "build_cached_edge_payloads_for_ids", return_value=[second, third]):
                sync.replace_cached_edge_payloads({"e2", "e3"}, set())
            self.assertEqual(cache.edge_only_reindex_call_count, 1)

        with self.subTest("simultaneous add remove"):
            workspace = SimpleNamespace(
                nodes={},
                edges={"e2": SimpleNamespace(edge_id="e2"), "e3": SimpleNamespace(edge_id="e3")},
            )
            cache = _GraphScenePayloadCache(edges=[first, second])
            cache.rebuild_indexes()
            context = _FakeContext(cache, workspace)
            sync = ScenePayloadCacheSync(context)
            with patch.object(sync, "build_cached_edge_payloads_for_ids", return_value=[third]):
                sync.replace_cached_edge_payloads({"e3"}, {"e1"})
            self.assertEqual(cache.edge_only_reindex_call_count, 1)

    def test_builder_and_identity_failures_keep_reindex_fallback(self) -> None:
        first = _edge_payload("e1", "n1", "out", "n2", "in")
        added = _edge_payload("e2", "n2", "out", "n3", "in")

        with self.subTest("builder fallback"):
            workspace = SimpleNamespace(
                nodes={},
                edges={"e1": SimpleNamespace(edge_id="e1"), "e2": SimpleNamespace(edge_id="e2")},
            )
            cache = _GraphScenePayloadCache(edges=[first])
            cache.rebuild_indexes()
            context = _FakeContext(cache, workspace)
            sync = ScenePayloadCacheSync(context)
            with patch.object(sync, "build_cached_edge_payloads_for_ids", return_value=None):
                with patch.object(
                    context._payload_builder,
                    "build_edge_payloads_for_ids",
                    return_value=[added],
                    create=True,
                ):
                    sync.replace_cached_edge_payloads({"e2"}, set())
            self.assertEqual(cache.edge_only_reindex_call_count, 1)

        with self.subTest("identity mismatch"):
            workspace = SimpleNamespace(nodes={}, edges={"e1": SimpleNamespace(edge_id="e1")})
            cache = _GraphScenePayloadCache(edges=[first])
            cache.rebuild_indexes()
            cache.edge_payload_by_id["e1"] = dict(first)
            context = _FakeContext(cache, workspace)
            sync = ScenePayloadCacheSync(context)
            with patch.object(sync, "build_cached_edge_payloads_for_ids", return_value=[dict(first)]):
                sync.replace_cached_edge_payloads({"e1"}, set())
            self.assertEqual(cache.edge_only_reindex_call_count, 1)

    def test_workspace_membership_and_order_guards_keep_reindex_fallback(self) -> None:
        first = _edge_payload("e1", "n1", "out", "n2", "in")
        second = _edge_payload("e2", "n2", "out", "n3", "in")

        with self.subTest("added edge absent from workspace"):
            workspace = SimpleNamespace(nodes={}, edges={"e1": SimpleNamespace(edge_id="e1")})
            cache = _GraphScenePayloadCache(edges=[first])
            cache.rebuild_indexes()
            context = _FakeContext(cache, workspace)
            sync = ScenePayloadCacheSync(context)
            with patch.object(sync, "build_cached_edge_payloads_for_ids", return_value=[second]):
                sync.replace_cached_edge_payloads({"e2"}, set())
            self.assertEqual(cache.edge_only_reindex_call_count, 1)

        with self.subTest("removed edge still present in workspace"):
            workspace = SimpleNamespace(
                nodes={},
                edges={"e1": SimpleNamespace(edge_id="e1"), "e2": SimpleNamespace(edge_id="e2")},
            )
            cache = _GraphScenePayloadCache(edges=[first, second])
            cache.rebuild_indexes()
            context = _FakeContext(cache, workspace)
            ScenePayloadCacheSync(context).replace_cached_edge_payloads(set(), {"e1"})
            self.assertEqual(cache.edge_only_reindex_call_count, 1)

        with self.subTest("noncanonical edge order"):
            third = _edge_payload("e3", "n3", "out", "n4", "in")
            workspace = SimpleNamespace(
                nodes={},
                edges={edge_id: SimpleNamespace(edge_id=edge_id) for edge_id in ("e1", "e2", "e3")},
            )
            cache = _GraphScenePayloadCache(edges=[second, first])
            cache.rebuild_indexes()
            context = _FakeContext(cache, workspace)
            sync = ScenePayloadCacheSync(context)
            with patch.object(sync, "build_cached_edge_payloads_for_ids", return_value=[third]):
                sync.replace_cached_edge_payloads({"e3"}, set())
            self.assertEqual(cache.edge_only_reindex_call_count, 1)


if __name__ == "__main__":
    unittest.main()
