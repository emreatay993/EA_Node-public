from __future__ import annotations

"""Group-backdrop payload contributions.

Group backdrops carry no per-node payload tail today: their model-level
behavior (partitioning, membership, collapse proxies, occupied bounds) is
owned by ``graph_scene_payload.backdrop_partitioner``. When a backdrop-only
payload field is needed, add ``contribute`` here and register it in
``kinds.kind_dispatch_for_spec`` — do not branch in the factory or grow the
partitioner's per-node knowledge.
"""
