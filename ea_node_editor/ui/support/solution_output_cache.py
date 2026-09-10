# Purpose: Bound shell output observations and select the runtime-retained record.
# Map: feature_routes/node_execution_visualization.md
# Tests: tests/test_run_projection_controller.py
from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from ea_node_editor.runtime_contracts.settled_results import SettledPortResult, settled_outputs_to_payload

MAX_RECORDS_PER_NODE = 2
MAX_RECORDS_PER_WORKSPACE = 4_096
MAX_PAYLOAD_BYTES_PER_WORKSPACE = 536_870_912
MAX_RECORDS_GLOBAL = 16_384
MAX_PAYLOAD_BYTES_GLOBAL = 2_147_483_648


def current_output_value(run_state: object, workspace_id: str, node_id: str, port_key: str) -> Any:
    """Read only the current accepted, available value for one output port."""
    record = retained_output_record(run_state, workspace_id, node_id, current_only=True)
    if record is None or not record.get("outputs_available", False):
        return None
    result = record.get("outputs", {}).get(port_key)
    return result.value if isinstance(result, SettledPortResult) and result.status == "value" else None


def retained_output_record(
    run_state: object | None,
    workspace_id: str,
    node_id: str,
    *,
    current_only: bool = False,
) -> dict[str, Any] | None:
    workspace_key = str(workspace_id or "").strip()
    node_key = str(node_id or "").strip()
    facts_by_workspace = getattr(
        run_state, "node_solution_facts_by_workspace_id", {}
    )
    facts = (
        facts_by_workspace.get(workspace_key, {})
        if isinstance(facts_by_workspace, Mapping)
        else {}
    )
    fact = facts.get(node_key) if isinstance(facts, Mapping) else None
    records_by_workspace = getattr(
        run_state, "cached_node_output_records_by_workspace_id", {}
    )
    records_by_node = (
        records_by_workspace.get(workspace_key, {})
        if isinstance(records_by_workspace, Mapping)
        else {}
    )
    records = (
        records_by_node.get(node_key, {})
        if isinstance(records_by_node, Mapping)
        else {}
    )
    return retained_output_record_from_records(
        records,
        fact,
        current_only=current_only,
    )


def retained_output_record_from_records(
    records: object,
    fact: object | None,
    *,
    current_only: bool = False,
) -> dict[str, Any] | None:
    freshness = str(getattr(getattr(fact, "freshness", ""), "value", "") or "")
    record_id = str(getattr(fact, "retained_record_id", "") or "").strip()
    if not record_id or (current_only and freshness != "current"):
        return None
    record = records.get(record_id) if isinstance(records, Mapping) else None
    if not isinstance(record, Mapping) or str(record.get("record_id", "")) != record_id:
        return None
    projected = dict(record)
    projected["stale"] = freshness == "expired"
    projected["stale_reason"] = (
        str(getattr(fact, "expiration_reason_code", "") or "")
        if freshness == "expired"
        else ""
    )
    return projected


def retained_output_records_by_node(
    run_state: object | None,
    workspace_id: str,
    *,
    current_only: bool = False,
) -> dict[str, dict[str, dict[str, Any]]]:
    workspace_key = str(workspace_id or "").strip()
    facts_by_workspace = getattr(
        run_state, "node_solution_facts_by_workspace_id", {}
    )
    facts = (
        facts_by_workspace.get(workspace_key, {})
        if isinstance(facts_by_workspace, Mapping)
        else {}
    )
    if not isinstance(facts, Mapping):
        return {}
    result: dict[str, dict[str, dict[str, Any]]] = {}
    for node_id in facts:
        record = retained_output_record(
            run_state,
            workspace_key,
            str(node_id),
            current_only=current_only,
        )
        if record is not None:
            result[str(node_id)] = {str(record["record_id"]): record}
    return result


def cache_accepted_output_record(
    run_state: Any,
    *,
    workspace_id: str,
    node_id: str,
    event: Mapping[str, Any],
    outputs: Mapping[str, Any],
    catalog: Any,
) -> bool:
    workspace_key = str(workspace_id or "").strip()
    node_key = str(node_id or "").strip()
    record_id = str(event.get("record_id", "") or "").strip()
    solution_key = str(event.get("solution_key", "") or "").strip()
    result_digest = str(event.get("result_digest", "") or "").strip()
    disposition = str(event.get("disposition", "") or "").strip()
    if not all((workspace_key, node_key, record_id, solution_key, result_digest, disposition)):
        return False

    run_state.node_output_cache_sequence += 1
    sequence = int(run_state.node_output_cache_sequence)
    run_counts = run_state.node_output_run_counts_by_workspace_id.setdefault(
        workspace_key, {}
    )
    run_counts[node_key] = int(run_counts.get(node_key, 0)) + 1
    try:
        encoded_outputs = json.dumps(
            settled_outputs_to_payload(outputs, catalog=catalog),
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError):
        encoded_outputs = b""
    outputs_available = bool(encoded_outputs)
    payload_bytes = len(encoded_outputs)
    if payload_bytes > min(
        MAX_PAYLOAD_BYTES_PER_WORKSPACE, MAX_PAYLOAD_BYTES_GLOBAL
    ):
        outputs_available = False
        payload_bytes = 0

    record: dict[str, Any] = {
        "record_id": record_id,
        "solution_key": solution_key,
        "result_digest": result_digest,
        "disposition": disposition,
        "run_id": str(event.get("run_id", "") or ""),
        "observed_at_epoch_ms": float(event.get("observed_at_epoch_ms", 0.0) or 0.0),
        "outputs": dict(outputs) if outputs_available else {},
        "outputs_available": outputs_available,
        "payload_bytes": payload_bytes,
        "cache_sequence": sequence,
    }
    records = run_state.cached_node_output_records_by_workspace_id.setdefault(
        workspace_key, {}
    ).setdefault(node_key, {})
    records[record_id] = record
    _enforce_limits(run_state, workspace_key, node_key, record_id)
    return record_id in records


def remove_cached_nodes(run_state: Any, workspace_id: str, node_ids: object) -> None:
    workspace_key = str(workspace_id or "").strip()
    normalized = {
        str(node_id or "").strip()
        for node_id in node_ids if str(node_id or "").strip()
    } if isinstance(node_ids, (set, frozenset, list, tuple)) else set()
    records_by_node = run_state.cached_node_output_records_by_workspace_id.get(
        workspace_key, {}
    )
    counts_by_node = run_state.node_output_run_counts_by_workspace_id.get(
        workspace_key, {}
    )
    for node_id in normalized:
        records_by_node.pop(node_id, None)
        counts_by_node.pop(node_id, None)
    if not records_by_node:
        run_state.cached_node_output_records_by_workspace_id.pop(workspace_key, None)
    if not counts_by_node:
        run_state.node_output_run_counts_by_workspace_id.pop(workspace_key, None)


def _pinned_record_ids(run_state: Any) -> set[str]:
    return {
        str(getattr(fact, "retained_record_id", "") or "")
        for facts in run_state.node_solution_facts_by_workspace_id.values()
        for fact in facts.values()
        if str(getattr(fact, "retained_record_id", "") or "")
    }


def _entries(run_state: Any):  # noqa: ANN202
    for workspace_id, records_by_node in (
        run_state.cached_node_output_records_by_workspace_id.items()
    ):
        for node_id, records in records_by_node.items():
            for record_id, record in records.items():
                yield workspace_id, node_id, record_id, record


def _remove_entry(run_state: Any, workspace_id: str, node_id: str, record_id: str) -> None:
    records_by_node = run_state.cached_node_output_records_by_workspace_id.get(
        workspace_id, {}
    )
    records = records_by_node.get(node_id, {})
    records.pop(record_id, None)
    if not records:
        records_by_node.pop(node_id, None)
    if not records_by_node:
        run_state.cached_node_output_records_by_workspace_id.pop(workspace_id, None)


def _oldest(entries: list[tuple[str, str, str, Mapping[str, Any]]]):
    return min(
        entries,
        key=lambda item: (
            int(item[3].get("cache_sequence", 0) or 0),
            item[0],
            item[1],
            item[2],
        ),
    )


def _enforce_limits(
    run_state: Any,
    workspace_id: str,
    node_id: str,
    candidate_record_id: str,
) -> None:
    pinned = _pinned_record_ids(run_state)
    while True:
        entries = list(_entries(run_state))
        node_entries = [item for item in entries if item[:2] == (workspace_id, node_id)]
        workspace_entries = [item for item in entries if item[0] == workspace_id]
        workspace_bytes = sum(int(item[3].get("payload_bytes", 0) or 0) for item in workspace_entries)
        global_bytes = sum(int(item[3].get("payload_bytes", 0) or 0) for item in entries)
        over_node = len(node_entries) > MAX_RECORDS_PER_NODE
        over_workspace = (
            len(workspace_entries) > MAX_RECORDS_PER_WORKSPACE
            or workspace_bytes > MAX_PAYLOAD_BYTES_PER_WORKSPACE
        )
        over_global = (
            len(entries) > MAX_RECORDS_GLOBAL
            or global_bytes > MAX_PAYLOAD_BYTES_GLOBAL
        )
        if not (over_node or over_workspace or over_global):
            return
        scope = node_entries if over_node else workspace_entries if over_workspace else entries
        evictable = [item for item in scope if item[2] not in pinned]
        if evictable:
            evicted = _oldest(evictable)
            _remove_entry(run_state, evicted[0], evicted[1], evicted[2])
            continue
        candidate = next(
            (item for item in entries if item[2] == candidate_record_id), None
        )
        if candidate is None:
            return
        candidate_record = candidate[3]
        if int(candidate_record.get("payload_bytes", 0) or 0):
            candidate_record["outputs"] = {}
            candidate_record["outputs_available"] = False
            candidate_record["payload_bytes"] = 0
            continue
        _remove_entry(run_state, candidate[0], candidate[1], candidate[2])
        return


__all__ = [
    "cache_accepted_output_record",
    "remove_cached_nodes",
    "retained_output_record",
    "retained_output_record_from_records",
    "retained_output_records_by_node",
]
