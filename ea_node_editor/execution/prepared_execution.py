# Purpose: Define immutable execution preparation and dispatch contracts.
# Map: subsystems/execution.md
# Tests: tests/test_solution_records.py, tests/test_runtime_current_results.py

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import InitVar, dataclass, fields
from enum import Enum
import hashlib
import json
from typing import TYPE_CHECKING, Any

from ea_node_editor.execution.backends import ExecutionBackendSelection
from ea_node_editor.execution.runtime_snapshot import RuntimeSnapshot
from ea_node_editor.runtime_contracts.data_types import DataTypeCatalog
from ea_node_editor.runtime_contracts.durable_values import (
    durable_settled_outputs_from_payload,
    durable_settled_outputs_to_payload,
    validate_durable_settled_outputs,
)
from ea_node_editor.runtime_contracts.value_codec import (
    deserialize_runtime_value,
    serialize_runtime_value,
)
from ea_node_editor.runtime_contracts.settled_results import (
    MAX_OUTPUTS_PER_NODE,
    SettledPortResult,
    normalize_settled_output_mapping,
    preflight_settled_output_mapping_payload,
    settled_output_mapping_from_payload,
    settled_outputs_to_payload,
)
from ea_node_editor.runtime_contracts.solution_records import (
    SolutionRecord,
    SolutionResidency,
)

if TYPE_CHECKING:
    from ea_node_editor.nodes.function_plugin import PluginBundleRef

MAX_PREPARED_NODES = 100_000
MAX_ACCEPTED_NODE_PAYLOADS_PER_PREPARATION = 100_000
MAX_ACCEPTED_PORT_RESULTS_PER_PREPARATION = 1_000_000
MAX_ACCEPTED_OUTPUT_PAYLOAD_BYTES = 67_108_864

_SESSION_ONLY_RUNTIME_MARKERS = frozenset(
    {
        "handle_ref",
        "tabular_data_ref",
        "array_data_ref",
        "tabular_window_ref",
        "array_slice_2d_ref",
        "secret_data",
        "ssh_sftp_host_data",
    }
)
_RUNTIME_VALUE_MARKER_KEY = "__ea_runtime_value__"


class PreparedAction(str, Enum):
    REUSE = "reuse"
    READ_CURRENT = "read_current"
    EXECUTE = "execute"
    PRUNE = "prune"

    @property
    def uses_accepted_output(self) -> bool:
        return self in {PreparedAction.REUSE, PreparedAction.READ_CURRENT}


class RecomputeMode(str, Enum):
    REUSE_VALID = "reuse_valid"
    FORCE_RECOMPUTE = "force_recompute"


def _exact_fields(
    payload: Mapping[str, Any], expected: frozenset[str], *, field_name: str
) -> None:
    if not isinstance(payload, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    actual = set(payload)
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected, key=str)
        details = []
        if missing:
            details.append(f"missing {missing}")
        if unexpected:
            details.append(f"unexpected {unexpected}")
        raise ValueError(f"{field_name} fields are invalid: {', '.join(details)}")


def _text(value: Any, *, field_name: str, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not allow_empty and not normalized:
        raise ValueError(f"{field_name} must be non-empty")
    if len(normalized.encode("utf-8")) > 1_024:
        raise ValueError(f"{field_name} exceeds 1024 bytes")
    return normalized


def _digest(value: Any, *, field_name: str) -> str:
    normalized = _text(value, field_name=field_name)
    if len(normalized) != 64 or any(
        char not in "0123456789abcdef" for char in normalized
    ):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")
    return normalized


def _integer(value: Any, *, field_name: str, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if (positive and value <= 0) or (not positive and value < 0):
        qualifier = "positive" if positive else "non-negative"
        raise ValueError(f"{field_name} must be {qualifier}")
    return value


def _enum(value: Any, enum_type: type[Enum], *, field_name: str) -> Any:
    try:
        return value if isinstance(value, enum_type) else enum_type(value)
    except (TypeError, ValueError) as exc:
        allowed = ", ".join(member.value for member in enum_type)
        raise ValueError(f"{field_name} must be one of: {allowed}") from exc


def _string_tuple(
    value: Any,
    *,
    field_name: str,
    digests: bool = False,
    limit: int = MAX_PREPARED_NODES,
) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise TypeError(f"{field_name} must be a list")
    if len(value) > limit:
        raise ValueError(f"{field_name} exceeds maximum count {limit}")
    normalized = tuple(
        _digest(item, field_name=f"{field_name}[{index}]")
        if digests
        else _text(item, field_name=f"{field_name}[{index}]")
        for index, item in enumerate(value)
    )
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{field_name} must not contain duplicates")
    return normalized


def normalize_trigger_publication_generations(
    value: Any,
) -> tuple[tuple[str, int], ...]:
    if not isinstance(value, (list, tuple)):
        raise TypeError("trigger_publication_generations must be a list")
    if len(value) > MAX_PREPARED_NODES:
        raise ValueError(
            "trigger_publication_generations exceeds maximum count "
            f"{MAX_PREPARED_NODES}"
        )
    normalized: list[tuple[str, int]] = []
    for index, item in enumerate(value):
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise TypeError(
                f"trigger_publication_generations[{index}] must be an id/generation pair"
            )
        normalized.append(
            (
                _text(
                    item[0],
                    field_name=f"trigger_publication_generations[{index}].node_id",
                ),
                _integer(
                    item[1],
                    field_name=f"trigger_publication_generations[{index}].generation",
                ),
            )
        )
    node_ids = tuple(node_id for node_id, _generation in normalized)
    if len(node_ids) != len(set(node_ids)):
        raise ValueError("trigger_publication_generations must not contain duplicates")
    return tuple(sorted(normalized))


def _canonical_json_bytes(value: Any, *, field_name: str) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{field_name} must contain strict JSON values") from exc


def _json_from_bytes(value: bytes, *, field_name: str) -> Any:
    if not isinstance(value, bytes):
        raise TypeError(f"{field_name} must be bytes")
    try:
        return json.loads(value.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{field_name} must contain canonical JSON") from exc


def _reject_durable_session_carriers(
    value: Any,
    *,
    catalog: DataTypeCatalog | None,
) -> None:
    if isinstance(value, Mapping):
        marker = value.get(_RUNTIME_VALUE_MARKER_KEY)
        if marker in _SESSION_ONLY_RUNTIME_MARKERS:
            raise ValueError("durable accepted outputs cannot contain session-only carriers")
        if marker == "artifact_ref" and value.get("scope") != "managed":
            raise ValueError("durable accepted outputs require managed artifact references")
        data_type_id = value.get("data_type_id")
        if marker in {"artifact_ref", "typed_inline", "image_value"}:
            if catalog is None:
                raise ValueError(
                    "durable accepted outputs with typed carriers require a catalog"
                )
            if not isinstance(data_type_id, str):
                raise ValueError("durable typed carriers require data_type_id")
            spec = catalog.require(data_type_id)
            if spec.persistence == "never" or spec.sensitivity != "normal":
                raise ValueError(
                    "durable accepted outputs cannot contain session-only carriers"
                )
        for item in value.values():
            _reject_durable_session_carriers(item, catalog=catalog)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _reject_durable_session_carriers(item, catalog=catalog)


def _settled_outputs_bytes(
    value: Mapping[str, SettledPortResult] | bytes,
    *,
    catalog: DataTypeCatalog | None,
    field_name: str,
) -> bytes:
    if isinstance(value, bytes):
        raw = _json_from_bytes(value, field_name=field_name)
        preflight_settled_output_mapping_payload(raw)
        settled_output_mapping_from_payload(raw, catalog=catalog)
        return _canonical_json_bytes(raw, field_name=field_name)
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping or bytes")
    if len(value) > MAX_OUTPUTS_PER_NODE:
        raise ValueError(
            f"{field_name} exceeds maximum count {MAX_OUTPUTS_PER_NODE}"
        )
    payload = settled_outputs_to_payload(value, catalog=catalog)
    preflight_settled_output_mapping_payload(payload)
    return _canonical_json_bytes(payload, field_name=field_name)


def _decode_settled_outputs_bytes(
    value: bytes,
    *,
    catalog: DataTypeCatalog | None,
    field_name: str,
) -> dict[str, SettledPortResult]:
    return settled_output_mapping_from_payload(
        _json_from_bytes(value, field_name=field_name),
        catalog=catalog,
    )


@dataclass(slots=True, frozen=True, kw_only=True)
class PreparedDispatchEnvelope:
    project_path: str
    project_id: str
    workspace_id: str
    trigger: Mapping[str, Any] | bytes
    runtime_snapshot: RuntimeSnapshot | bytes
    execution_backend: ExecutionBackendSelection
    target_node_ids: tuple[str, ...]
    clicked_trigger_node_id: str
    trigger_capture_node_ids: tuple[str, ...]
    trigger_publications: Mapping[str, SettledPortResult] | bytes
    trigger_captures: Mapping[str, SettledPortResult] | bytes
    recompute_mode: RecomputeMode
    developer_mode: bool
    catalog_fingerprint: str
    catalog_revisions: tuple[Any, ...]
    plugin_bundles: tuple[PluginBundleRef, ...]
    plugin_fingerprint: str
    runtime_registry_fingerprint: str
    registry_contract_fingerprint: str
    addon_runtime_config: tuple[tuple[str, bool], ...]
    catalog: InitVar[DataTypeCatalog | None] = None

    def __post_init__(self, catalog: DataTypeCatalog | None) -> None:
        object.__setattr__(
            self,
            "project_path",
            _text(self.project_path, field_name="project_path", allow_empty=True),
        )
        for field_name in ("project_id", "workspace_id"):
            object.__setattr__(
                self,
                field_name,
                _text(getattr(self, field_name), field_name=field_name),
            )
        if isinstance(self.trigger, bytes):
            trigger_payload = _json_from_bytes(self.trigger, field_name="trigger")
        elif isinstance(self.trigger, Mapping):
            trigger_payload = serialize_runtime_value(self.trigger, catalog=catalog)
        else:
            raise TypeError("trigger must be a mapping or bytes")
        decoded_trigger = deserialize_runtime_value(trigger_payload, catalog=catalog)
        if not isinstance(decoded_trigger, Mapping):
            raise TypeError("trigger must decode to a mapping")
        if isinstance(self.runtime_snapshot, RuntimeSnapshot):
            snapshot_payload = self.runtime_snapshot.to_document(catalog=catalog)
        elif isinstance(self.runtime_snapshot, bytes):
            snapshot_payload = _json_from_bytes(
                self.runtime_snapshot,
                field_name="runtime_snapshot",
            )
        else:
            raise TypeError("runtime_snapshot must be a RuntimeSnapshot or bytes")
        if not isinstance(snapshot_payload, Mapping):
            raise TypeError("runtime_snapshot must encode a mapping")
        snapshot = RuntimeSnapshot.from_mapping(snapshot_payload, catalog=catalog)
        if snapshot.project_id != self.project_id:
            raise ValueError("runtime_snapshot project_id must match project_id")
        try:
            snapshot.workspace(self.workspace_id)
        except KeyError as exc:
            raise ValueError("runtime_snapshot must contain workspace_id") from exc
        object.__setattr__(
            self,
            "runtime_snapshot",
            _canonical_json_bytes(
                snapshot.to_document(catalog=catalog),
                field_name="runtime_snapshot",
            ),
        )
        if not isinstance(self.execution_backend, ExecutionBackendSelection):
            raise TypeError("execution_backend must be an ExecutionBackendSelection")
        object.__setattr__(
            self,
            "target_node_ids",
            _string_tuple(self.target_node_ids, field_name="target_node_ids"),
        )
        object.__setattr__(
            self,
            "clicked_trigger_node_id",
            _text(
                self.clicked_trigger_node_id,
                field_name="clicked_trigger_node_id",
                allow_empty=True,
            ),
        )
        object.__setattr__(
            self,
            "trigger_capture_node_ids",
            _string_tuple(
                self.trigger_capture_node_ids,
                field_name="trigger_capture_node_ids",
            ),
        )
        object.__setattr__(
            self,
            "trigger",
            _canonical_json_bytes(trigger_payload, field_name="trigger"),
        )
        object.__setattr__(
            self,
            "trigger_publications",
            _settled_outputs_bytes(
                self.trigger_publications,
                catalog=catalog,
                field_name="trigger_publications",
            ),
        )
        object.__setattr__(
            self,
            "trigger_captures",
            _settled_outputs_bytes(
                self.trigger_captures,
                catalog=catalog,
                field_name="trigger_captures",
            ),
        )
        object.__setattr__(
            self,
            "recompute_mode",
            _enum(self.recompute_mode, RecomputeMode, field_name="recompute_mode"),
        )
        if not isinstance(self.developer_mode, bool):
            raise TypeError("developer_mode must be a boolean")
        for field_name in (
            "catalog_fingerprint",
            "plugin_fingerprint",
            "runtime_registry_fingerprint",
            "registry_contract_fingerprint",
        ):
            object.__setattr__(
                self,
                field_name,
                _digest(getattr(self, field_name), field_name=field_name),
            )
        if not isinstance(self.catalog_revisions, tuple):
            raise TypeError("catalog_revisions must be a tuple")
        if not isinstance(self.plugin_bundles, tuple):
            raise TypeError("plugin_bundles must be a tuple")
        if not isinstance(self.addon_runtime_config, (list, tuple)):
            raise TypeError("addon_runtime_config must be a list")
        addon_runtime_config = []
        seen_addons: set[str] = set()
        for index, pair in enumerate(self.addon_runtime_config):
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                raise TypeError(
                    f"addon_runtime_config[{index}] must be an id/bool pair"
                )
            addon_id = _text(pair[0], field_name=f"addon_runtime_config[{index}].id")
            if not isinstance(pair[1], bool):
                raise TypeError(
                    f"addon_runtime_config[{index}].enabled must be a boolean"
                )
            if addon_id in seen_addons:
                raise ValueError("addon_runtime_config must not contain duplicate IDs")
            seen_addons.add(addon_id)
            addon_runtime_config.append((addon_id, pair[1]))
        object.__setattr__(self, "addon_runtime_config", tuple(addon_runtime_config))

    def _to_payload(
        self, *, catalog: DataTypeCatalog | None = None
    ) -> dict[str, Any]:
        from ea_node_editor.execution.run_messages import StartRunCommand
        from ea_node_editor.execution.protocol_codec import command_to_dict

        runtime_snapshot = self.decode_runtime_snapshot(catalog=catalog)
        command_payload = command_to_dict(
            StartRunCommand(
                run_id="prepared",
                project_path=self.project_path,
                workspace_id=self.workspace_id,
                trigger=self.decode_trigger(catalog=catalog),
                runtime_snapshot=runtime_snapshot,
                execution_backend=self.execution_backend,
                target_node_ids=self.target_node_ids,
                recompute_mode=self.recompute_mode.value,
                clicked_trigger_node_id=self.clicked_trigger_node_id,
                trigger_publications=self.decode_trigger_publications(
                    catalog=catalog
                ),
                trigger_captures=self.decode_trigger_captures(catalog=catalog),
                developer_mode=self.developer_mode,
                catalog_fingerprint=self.catalog_fingerprint,
                catalog_revisions=self.catalog_revisions,
                plugin_bundles=self.plugin_bundles,
                plugin_fingerprint=self.plugin_fingerprint,
                runtime_registry_fingerprint=self.runtime_registry_fingerprint,
                registry_contract_fingerprint=self.registry_contract_fingerprint,
                addon_runtime_config=self.addon_runtime_config,
            ),
            catalog=catalog,
        )
        command_payload.pop("type", None)
        command_payload.pop("run_id", None)
        for field_name in (
            "preparation_id",
            "solution_namespace_id",
            "execution_affecting_workspace_revision",
            "dispatch_runtime_generation",
            "runtime_snapshot_fingerprint",
            "execution_plan_fingerprint",
            "workflow_interface_revision",
            "workflow_interface_digest",
            "execution_environment_digest",
            "trigger_publication_generations",
            "node_decisions",
            "accepted_output_payloads",
            "viewer_invalidation_node_ids",
            "viewer_workspace_invalidation_epoch",
            "viewer_node_invalidation_epochs",
            "viewer_invalidation_reservation_id",
            "viewer_epoch_snapshot_digest",
        ):
            command_payload.pop(field_name, None)
        command_payload.update(
            {
                "project_id": self.project_id,
                "trigger_capture_node_ids": list(self.trigger_capture_node_ids),
                "recompute_mode": self.recompute_mode.value,
            }
        )
        return command_payload

    def decode_runtime_snapshot(
        self,
        *,
        catalog: DataTypeCatalog | None = None,
    ) -> RuntimeSnapshot:
        payload = _json_from_bytes(
            self.runtime_snapshot,
            field_name="runtime_snapshot",
        )
        if not isinstance(payload, Mapping):
            raise ValueError("runtime_snapshot must decode to a mapping")
        return RuntimeSnapshot.from_mapping(payload, catalog=catalog)

    def decode_trigger(
        self,
        *,
        catalog: DataTypeCatalog | None = None,
    ) -> dict[str, Any]:
        payload = _json_from_bytes(self.trigger, field_name="trigger")
        decoded = deserialize_runtime_value(payload, catalog=catalog)
        if not isinstance(decoded, Mapping):
            raise ValueError("trigger must decode to a mapping")
        return dict(decoded)

    def decode_trigger_publications(
        self,
        *,
        catalog: DataTypeCatalog | None = None,
    ) -> dict[str, SettledPortResult]:
        return _decode_settled_outputs_bytes(
            self.trigger_publications,
            catalog=catalog,
            field_name="trigger_publications",
        )

    def decode_trigger_captures(
        self,
        *,
        catalog: DataTypeCatalog | None = None,
    ) -> dict[str, SettledPortResult]:
        return _decode_settled_outputs_bytes(
            self.trigger_captures,
            catalog=catalog,
            field_name="trigger_captures",
        )

    def to_payload(
        self, *, catalog: DataTypeCatalog | None = None
    ) -> dict[str, Any]:
        payload = self._to_payload(catalog=catalog)
        return self.from_payload(payload, catalog=catalog)._to_payload(catalog=catalog)

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, Any],
        *,
        catalog: DataTypeCatalog | None = None,
    ) -> PreparedDispatchEnvelope:
        _exact_fields(payload, _DISPATCH_FIELDS, field_name="prepared dispatch envelope")
        from ea_node_editor.execution.run_messages import StartRunCommand
        from ea_node_editor.execution.protocol_codec import dict_to_command

        command_payload = {
            key: value
            for key, value in payload.items()
            if key not in {"project_id", "trigger_capture_node_ids"}
        }
        command_payload.update({"type": "start_run", "run_id": "prepared"})
        command = dict_to_command(command_payload, catalog=catalog)
        if not isinstance(command, StartRunCommand):
            raise ValueError("prepared dispatch envelope must decode a start command")
        return cls(
            project_path=command.project_path,
            project_id=payload["project_id"],
            workspace_id=command.workspace_id,
            trigger=command.trigger,
            runtime_snapshot=_canonical_json_bytes(
                payload["runtime_snapshot"],
                field_name="runtime_snapshot",
            ),
            execution_backend=command.execution_backend,
            target_node_ids=command.target_node_ids,
            clicked_trigger_node_id=command.clicked_trigger_node_id,
            trigger_capture_node_ids=payload["trigger_capture_node_ids"],
            trigger_publications=command.trigger_publications,
            trigger_captures=command.trigger_captures,
            recompute_mode=payload["recompute_mode"],
            developer_mode=command.developer_mode,
            catalog_fingerprint=command.catalog_fingerprint,
            catalog_revisions=command.catalog_revisions,
            plugin_bundles=command.plugin_bundles,
            plugin_fingerprint=command.plugin_fingerprint,
            runtime_registry_fingerprint=command.runtime_registry_fingerprint,
            registry_contract_fingerprint=command.registry_contract_fingerprint,
            addon_runtime_config=command.addon_runtime_config,
            catalog=catalog,
        )


@dataclass(slots=True, frozen=True)
class PreparedNodeDecision:
    node_id: str
    action: PreparedAction
    reason_code: str
    solution_key: str
    dependency_solution_keys: tuple[str, ...]
    accepted_record_id: str | None = None
    accepted_payload_digest: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "node_id", _text(self.node_id, field_name="node_id"))
        action = _enum(self.action, PreparedAction, field_name="action")
        reason = _text(self.reason_code, field_name="reason_code")
        object.__setattr__(
            self, "solution_key", _digest(self.solution_key, field_name="solution_key")
        )
        dependencies = _string_tuple(
            self.dependency_solution_keys,
            field_name="dependency_solution_keys",
            digests=True,
        )
        accepted_record_id = (
            None
            if self.accepted_record_id is None
            else _text(self.accepted_record_id, field_name="accepted_record_id")
        )
        if action.uses_accepted_output and accepted_record_id is None:
            raise ValueError("reuse decisions require accepted_record_id")
        if not action.uses_accepted_output and accepted_record_id is not None:
            raise ValueError("execute/prune decisions forbid accepted_record_id")
        if action.uses_accepted_output:
            object.__setattr__(
                self,
                "accepted_payload_digest",
                _digest(
                    self.accepted_payload_digest, field_name="accepted_payload_digest"
                ),
            )
        elif self.accepted_payload_digest is not None:
            raise ValueError("execute/prune decisions forbid output commitments")
        object.__setattr__(self, "action", action)
        object.__setattr__(self, "reason_code", reason)
        object.__setattr__(self, "dependency_solution_keys", dependencies)
        object.__setattr__(self, "accepted_record_id", accepted_record_id)

    def _to_payload(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "action": self.action.value,
            "reason_code": self.reason_code,
            "solution_key": self.solution_key,
            "dependency_solution_keys": list(self.dependency_solution_keys),
            "accepted_record_id": self.accepted_record_id,
            "accepted_payload_digest": self.accepted_payload_digest,
        }

    def to_payload(self) -> dict[str, Any]:
        return self.from_payload(self._to_payload())._to_payload()

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> PreparedNodeDecision:
        _exact_fields(payload, _DECISION_FIELDS, field_name="prepared node decision")
        return cls(**dict(payload))


@dataclass(slots=True, frozen=True, kw_only=True)
class AcceptedOutputPayload:
    """Transferred outputs, bound to their original complete result record.

    result_digest identifies the complete record; output_digest authenticates
    the transferred mapping, which may be a port subset for READ_CURRENT.
    """
    node_id: str
    record_id: str
    solution_key: str
    settlement_status: str
    result_digest: str
    residency: SolutionResidency
    runtime_generation: int | None
    outputs: Mapping[str, SettledPortResult] | bytes
    output_digest: str | None = None
    catalog: InitVar[DataTypeCatalog | None] = None

    def __post_init__(self, catalog: DataTypeCatalog | None) -> None:
        for field_name in ("node_id", "record_id"):
            object.__setattr__(
                self,
                field_name,
                _text(getattr(self, field_name), field_name=field_name),
            )
        object.__setattr__(
            self, "solution_key", _digest(self.solution_key, field_name="solution_key")
        )
        settlement_status = _text(
            self.settlement_status, field_name="settlement_status"
        )
        if settlement_status not in {"completed", "empty"}:
            raise ValueError("accepted outputs must be completed or empty")
        object.__setattr__(
            self,
            "result_digest",
            _digest(self.result_digest, field_name="result_digest"),
        )
        object.__setattr__(
            self,
            "output_digest",
            _digest(
                self.result_digest
                if self.output_digest is None
                else self.output_digest,
                field_name="output_digest",
            ),
        )
        residency = _enum(self.residency, SolutionResidency, field_name="residency")
        if residency is SolutionResidency.SESSION:
            if self.runtime_generation is None:
                raise ValueError("session accepted outputs require runtime_generation")
            _integer(
                self.runtime_generation,
                field_name="runtime_generation",
                positive=True,
            )
        elif self.runtime_generation is not None:
            raise ValueError("durable accepted outputs forbid runtime_generation")
        if isinstance(self.outputs, bytes):
            raw_outputs = _json_from_bytes(self.outputs, field_name="accepted outputs")
            preflight_settled_output_mapping_payload(
                raw_outputs,
                max_outputs=MAX_OUTPUTS_PER_NODE,
            )
            outputs = (
                durable_settled_outputs_from_payload(dict(raw_outputs))
                if residency is SolutionResidency.DURABLE
                else settled_output_mapping_from_payload(
                    raw_outputs,
                    catalog=catalog,
                    max_outputs=MAX_OUTPUTS_PER_NODE,
                )
            )
        elif isinstance(self.outputs, Mapping) and all(
            isinstance(result, SettledPortResult) for result in self.outputs.values()
        ):
            if len(self.outputs) > MAX_OUTPUTS_PER_NODE:
                raise ValueError(
                    "settled output mapping exceeds maximum count "
                    f"{MAX_OUTPUTS_PER_NODE}"
                )
            outputs = normalize_settled_output_mapping(
                self.outputs,
                max_outputs=MAX_OUTPUTS_PER_NODE,
            )
        else:
            preflight_settled_output_mapping_payload(
                self.outputs,
                max_outputs=MAX_OUTPUTS_PER_NODE,
            )
            outputs = (
                durable_settled_outputs_from_payload(dict(self.outputs))
                if residency is SolutionResidency.DURABLE
                else settled_output_mapping_from_payload(
                    self.outputs,
                    catalog=catalog,
                    max_outputs=MAX_OUTPUTS_PER_NODE,
                )
            )
        if any(result.status == "failed" for result in outputs.values()):
            raise ValueError("accepted outputs cannot contain failed port results")
        if settlement_status == "empty" and any(
            result.status != "empty" for result in outputs.values()
        ):
            raise ValueError("empty settlements cannot contain value port results")
        if (
            settlement_status == "completed"
            and outputs
            and not any(result.status == "value" for result in outputs.values())
        ):
            raise ValueError(
                "completed accepted outputs with ports require a value result"
            )
        output_payload = (
            durable_settled_outputs_to_payload(dict(outputs))
            if residency is SolutionResidency.DURABLE
            else settled_outputs_to_payload(outputs, catalog=catalog)
        )
        preflight_settled_output_mapping_payload(
            output_payload,
            max_outputs=MAX_OUTPUTS_PER_NODE,
        )
        if residency is SolutionResidency.DURABLE:
            _reject_durable_session_carriers(output_payload, catalog=catalog)
        object.__setattr__(self, "settlement_status", settlement_status)
        object.__setattr__(self, "residency", residency)
        object.__setattr__(
            self,
            "outputs",
            _canonical_json_bytes(output_payload, field_name="accepted outputs"),
        )

    @property
    def output_count(self) -> int:
        payload = _json_from_bytes(self.outputs, field_name="accepted outputs")
        if not isinstance(payload, Mapping):
            raise ValueError("accepted outputs must decode to a mapping")
        return len(payload)

    def commitment_digest(self) -> str:
        """Bind output bytes and their identity, status, and lifetime metadata."""
        metadata = {
            field.name: getattr(self, field.name)
            for field in fields(self)
            if field.name != "outputs"
        }
        return hashlib.sha256(
            _canonical_json_bytes(metadata, field_name="accepted output commitment")
        ).hexdigest()

    def select_ports(
        self,
        port_keys: tuple[str, ...],
        *,
        catalog: DataTypeCatalog,
    ) -> AcceptedOutputPayload:
        ports = _string_tuple(
            port_keys, field_name="current output ports", limit=MAX_OUTPUTS_PER_NODE
        )
        if not ports:
            raise ValueError("current results require a data-port dependency")
        original = _json_from_bytes(self.outputs, field_name="accepted outputs")
        if self.settlement_status == "empty" and not original:
            selected = {}
        else:
            if not set(ports).issubset(original):
                raise ValueError("current output port is unavailable")
            selected = {key: original[key] for key in ports}
        encoded = _canonical_json_bytes(selected, field_name="current outputs")
        return AcceptedOutputPayload(
            node_id=self.node_id,
            record_id=self.record_id,
            solution_key=self.solution_key,
            settlement_status="completed"
            if any(item["status"] == "value" for item in selected.values())
            else "empty",
            result_digest=self.result_digest,
            residency=self.residency,
            runtime_generation=self.runtime_generation,
            outputs=encoded,
            output_digest=hashlib.sha256(encoded).hexdigest(),
            catalog=catalog,
        )

    def decode_outputs(
        self,
        *,
        catalog: DataTypeCatalog | None = None,
    ) -> dict[str, SettledPortResult]:
        payload = _json_from_bytes(self.outputs, field_name="accepted outputs")
        return (
            durable_settled_outputs_from_payload(dict(payload))
            if self.residency is SolutionResidency.DURABLE
            else settled_output_mapping_from_payload(
                payload,
                catalog=catalog,
                max_outputs=MAX_OUTPUTS_PER_NODE,
            )
        )

    def _to_payload(
        self, *, catalog: DataTypeCatalog | None = None
    ) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "record_id": self.record_id,
            "solution_key": self.solution_key,
            "settlement_status": self.settlement_status,
            "result_digest": self.result_digest,
            "output_digest": self.output_digest,
            "residency": self.residency.value,
            "runtime_generation": self.runtime_generation,
            "outputs": _json_from_bytes(
                self.outputs,
                field_name="accepted outputs",
            ),
        }

    def to_payload(
        self, *, catalog: DataTypeCatalog | None = None
    ) -> dict[str, Any]:
        payload = self._to_payload(catalog=catalog)
        return self.from_payload(payload, catalog=catalog)._to_payload(catalog=catalog)

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, Any],
        *,
        catalog: DataTypeCatalog | None = None,
    ) -> AcceptedOutputPayload:
        _exact_fields(payload, _ACCEPTED_OUTPUT_FIELDS, field_name="accepted output payload")
        preflight_settled_output_mapping_payload(
            payload["outputs"],
            max_outputs=MAX_OUTPUTS_PER_NODE,
        )
        return cls(**dict(payload), catalog=catalog)


def validate_accepted_output_payload(
    record: SolutionRecord,
    payload: AcceptedOutputPayload,
    *,
    catalog: DataTypeCatalog | None = None,
    artifact_context: Any = None,
) -> None:
    if not isinstance(record, SolutionRecord):
        raise TypeError("record must be a SolutionRecord")
    if not isinstance(payload, AcceptedOutputPayload):
        raise TypeError("payload must be an AcceptedOutputPayload")
    if (
        record.node_id != payload.node_id
        or record.record_id != payload.record_id
        or record.solution_key != payload.solution_key
        or record.settlement_status != payload.settlement_status
        or record.result_digest != payload.result_digest
        or record.residency is not payload.residency
        or record.runtime_generation != payload.runtime_generation
    ):
        raise ValueError("accepted output payload binding does not match solution record")
    descriptor_statuses = {
        descriptor.port_key: descriptor.status
        for descriptor in record.output_descriptors
    }
    decoded_outputs = payload.decode_outputs(catalog=catalog)
    output_statuses = {
        port_key: result.status
        for port_key, result in decoded_outputs.items()
    }
    if descriptor_statuses != output_statuses:
        raise ValueError(
            "accepted output port keys and statuses must match solution descriptors"
        )
    if payload.output_digest != payload.result_digest:
        raise ValueError("computation reuse requires the complete recorded outputs")
    if record.residency is SolutionResidency.DURABLE and artifact_context is not None:
        if catalog is None:
            raise ValueError("durable accepted outputs require a data-type catalog")
        validation = validate_durable_settled_outputs(
            decoded_outputs,
            record.output_descriptors,
            catalog,
            artifact_context,
        )
        if not validation.eligible:
            raise ValueError(validation.reason_code)


def validate_current_output_payload(
    payload: AcceptedOutputPayload,
    *,
    catalog: DataTypeCatalog,
    port_keys: tuple[str, ...],
) -> None:
    """Require detached data; currentness is separately owned by SolutionStore.

    Reading a retained result must not revive handles, private working files,
    secrets, or session-bound typed snapshots after their producing run ends.
    This is a consumption check, not permission to persist the result.
    """
    outputs = payload.to_payload(catalog=catalog)["outputs"]
    if not port_keys or (
        set(outputs) != set(port_keys)
        and not (payload.settlement_status == "empty" and not outputs)
    ):
        raise ValueError("current outputs must match the required data ports")
    if hashlib.sha256(payload.outputs).hexdigest() != payload.output_digest:
        raise ValueError("current output payload digest is invalid")
    _reject_durable_session_carriers(outputs, catalog=catalog)


@dataclass(slots=True, frozen=True, kw_only=True)
class PreparedExecution:
    preparation_id: str
    dispatch_envelope: PreparedDispatchEnvelope
    solution_namespace_id: str
    execution_affecting_workspace_revision: int
    runtime_snapshot_fingerprint: str
    execution_plan_fingerprint: str
    registry_contract_fingerprint: str
    workflow_interface_revision: int
    workflow_interface_digest: str
    execution_environment_digest: str
    trigger_publication_generations: tuple[tuple[str, int], ...]
    node_decisions: tuple[PreparedNodeDecision, ...]
    accepted_output_payloads: tuple[AcceptedOutputPayload, ...]
    recompute_node_ids: tuple[str, ...]
    reused_node_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "preparation_id",
            _text(self.preparation_id, field_name="preparation_id"),
        )
        if not isinstance(self.dispatch_envelope, PreparedDispatchEnvelope):
            raise TypeError("dispatch_envelope must be a PreparedDispatchEnvelope")
        object.__setattr__(
            self,
            "solution_namespace_id",
            _text(self.solution_namespace_id, field_name="solution_namespace_id"),
        )
        _integer(
            self.execution_affecting_workspace_revision,
            field_name="execution_affecting_workspace_revision",
        )
        for field_name in (
            "runtime_snapshot_fingerprint",
            "execution_plan_fingerprint",
            "registry_contract_fingerprint",
            "workflow_interface_digest",
            "execution_environment_digest",
        ):
            object.__setattr__(
                self,
                field_name,
                _digest(getattr(self, field_name), field_name=field_name),
            )
        if (
            self.registry_contract_fingerprint
            != self.dispatch_envelope.registry_contract_fingerprint
        ):
            raise ValueError(
                "prepared registry fingerprint must match dispatch envelope"
            )
        _integer(
            self.workflow_interface_revision,
            field_name="workflow_interface_revision",
            positive=True,
        )
        object.__setattr__(
            self,
            "trigger_publication_generations",
            normalize_trigger_publication_generations(
                self.trigger_publication_generations
            ),
        )
        if not isinstance(self.node_decisions, (list, tuple)):
            raise TypeError("node_decisions must be a list")
        if len(self.node_decisions) > MAX_PREPARED_NODES:
            raise ValueError(
                f"node_decisions exceeds maximum count {MAX_PREPARED_NODES}"
            )
        decisions = tuple(self.node_decisions)
        if any(not isinstance(item, PreparedNodeDecision) for item in decisions):
            raise TypeError("node_decisions must contain PreparedNodeDecision values")
        node_ids = tuple(item.node_id for item in decisions)
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("node_decisions must not contain duplicate node IDs")
        solution_keys = tuple(item.solution_key for item in decisions)
        if len(solution_keys) != len(set(solution_keys)):
            raise ValueError("node_decisions cannot share cross-node solution keys")
        if not isinstance(self.accepted_output_payloads, (list, tuple)):
            raise TypeError("accepted_output_payloads must be a list")
        if (
            len(self.accepted_output_payloads)
            > MAX_ACCEPTED_NODE_PAYLOADS_PER_PREPARATION
        ):
            raise ValueError(
                "accepted_output_payloads exceeds maximum count "
                f"{MAX_ACCEPTED_NODE_PAYLOADS_PER_PREPARATION}"
            )
        accepted = tuple(self.accepted_output_payloads)
        if any(not isinstance(item, AcceptedOutputPayload) for item in accepted):
            raise TypeError(
                "accepted_output_payloads must contain AcceptedOutputPayload values"
            )
        accepted_by_node = {item.node_id: item for item in accepted}
        if len(accepted_by_node) != len(accepted):
            raise ValueError(
                "accepted_output_payloads must not contain duplicate nodes"
            )
        accepted_record_ids = tuple(item.record_id for item in accepted)
        if len(accepted_record_ids) != len(set(accepted_record_ids)):
            raise ValueError("accepted_output_payloads must not duplicate record IDs")
        accepted_solution_keys = tuple(item.solution_key for item in accepted)
        if len(accepted_solution_keys) != len(set(accepted_solution_keys)):
            raise ValueError(
                "accepted_output_payloads cannot share cross-node solution keys"
            )
        reuse_node_ids = {
            item.node_id for item in decisions if item.action.uses_accepted_output
        }
        if set(accepted_by_node) != reuse_node_ids:
            raise ValueError(
                "accepted output payloads require exactly the matching reuse decisions"
            )
        port_count = sum(item.output_count for item in accepted)
        if port_count > MAX_ACCEPTED_PORT_RESULTS_PER_PREPARATION:
            raise ValueError(
                "accepted output port results exceed maximum count "
                f"{MAX_ACCEPTED_PORT_RESULTS_PER_PREPARATION}"
            )
        for decision in decisions:
            payload = accepted_by_node.get(decision.node_id)
            if not decision.action.uses_accepted_output:
                if payload is not None:
                    raise ValueError(
                        "execute/prune decisions cannot have accepted outputs"
                    )
                continue
            if payload is None:
                raise ValueError("reuse decisions require one accepted output payload")
            if (
                payload.record_id != decision.accepted_record_id
                or payload.solution_key != decision.solution_key
                or payload.commitment_digest() != decision.accepted_payload_digest
            ):
                raise ValueError(
                    "accepted output payload must match decision record and solution key"
                )
        recompute = _string_tuple(
            self.recompute_node_ids,
            field_name="recompute_node_ids",
        )
        reused = _string_tuple(self.reused_node_ids, field_name="reused_node_ids")
        expected_recompute = tuple(
            item.node_id for item in decisions if item.action is PreparedAction.EXECUTE
        )
        expected_reused = tuple(
            item.node_id for item in decisions if item.action.uses_accepted_output
        )
        if recompute != expected_recompute or reused != expected_reused:
            raise ValueError("prepared recompute/reused node IDs must match decisions")
        object.__setattr__(self, "node_decisions", decisions)
        object.__setattr__(self, "accepted_output_payloads", accepted)
        object.__setattr__(self, "recompute_node_ids", recompute)
        object.__setattr__(self, "reused_node_ids", reused)

    def _to_payload(
        self, *, catalog: DataTypeCatalog | None = None
    ) -> dict[str, Any]:
        return {
            "preparation_id": self.preparation_id,
            "dispatch_envelope": self.dispatch_envelope._to_payload(catalog=catalog),
            "solution_namespace_id": self.solution_namespace_id,
            "execution_affecting_workspace_revision": self.execution_affecting_workspace_revision,
            "runtime_snapshot_fingerprint": self.runtime_snapshot_fingerprint,
            "execution_plan_fingerprint": self.execution_plan_fingerprint,
            "registry_contract_fingerprint": self.registry_contract_fingerprint,
            "workflow_interface_revision": self.workflow_interface_revision,
            "workflow_interface_digest": self.workflow_interface_digest,
            "execution_environment_digest": self.execution_environment_digest,
            "trigger_publication_generations": [
                [node_id, generation]
                for node_id, generation in self.trigger_publication_generations
            ],
            "node_decisions": [item._to_payload() for item in self.node_decisions],
            "accepted_output_payloads": [
                item._to_payload(catalog=catalog)
                for item in self.accepted_output_payloads
            ],
            "recompute_node_ids": list(self.recompute_node_ids),
            "reused_node_ids": list(self.reused_node_ids),
        }

    def to_payload(
        self, *, catalog: DataTypeCatalog | None = None
    ) -> dict[str, Any]:
        payload = self._to_payload(catalog=catalog)
        return self.from_payload(payload, catalog=catalog)._to_payload(catalog=catalog)

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, Any],
        *,
        catalog: DataTypeCatalog | None = None,
    ) -> PreparedExecution:
        _exact_fields(payload, _PREPARED_EXECUTION_FIELDS, field_name="prepared execution")
        raw_decisions = payload["node_decisions"]
        raw_accepted = payload["accepted_output_payloads"]
        if not isinstance(raw_decisions, (list, tuple)):
            raise TypeError("node_decisions must be a list")
        if not isinstance(raw_accepted, (list, tuple)):
            raise TypeError("accepted_output_payloads must be a list")
        if len(raw_decisions) > MAX_PREPARED_NODES:
            raise ValueError(
                f"node_decisions exceeds maximum count {MAX_PREPARED_NODES}"
            )
        if len(raw_accepted) > MAX_ACCEPTED_NODE_PAYLOADS_PER_PREPARATION:
            raise ValueError(
                "accepted_output_payloads exceeds maximum count "
                f"{MAX_ACCEPTED_NODE_PAYLOADS_PER_PREPARATION}"
            )
        raw_decision_node_ids: list[str] = []
        raw_decision_solution_keys: list[str] = []
        for raw_decision in raw_decisions:
            _exact_fields(
                raw_decision,
                _DECISION_FIELDS,
                field_name="prepared node decision",
            )
            raw_decision_node_ids.append(
                _text(raw_decision["node_id"], field_name="node_id")
            )
            raw_decision_solution_keys.append(
                _digest(raw_decision["solution_key"], field_name="solution_key")
            )
        if len(raw_decision_node_ids) != len(set(raw_decision_node_ids)):
            raise ValueError("node_decisions must not contain duplicate node IDs")
        if len(raw_decision_solution_keys) != len(set(raw_decision_solution_keys)):
            raise ValueError("node_decisions cannot share cross-node solution keys")
        raw_port_count = 0
        raw_record_ids: list[str] = []
        raw_accepted_solution_keys: list[str] = []
        for raw_output in raw_accepted:
            _exact_fields(
                raw_output,
                _ACCEPTED_OUTPUT_FIELDS,
                field_name="accepted output payload",
            )
            raw_port_count += preflight_settled_output_mapping_payload(
                raw_output["outputs"],
                max_outputs=MAX_OUTPUTS_PER_NODE,
            )
            if raw_port_count > MAX_ACCEPTED_PORT_RESULTS_PER_PREPARATION:
                raise ValueError(
                    "accepted output port results exceed maximum count "
                    f"{MAX_ACCEPTED_PORT_RESULTS_PER_PREPARATION}"
                )
            raw_record_ids.append(
                _text(raw_output["record_id"], field_name="record_id")
            )
            raw_accepted_solution_keys.append(
                _digest(raw_output["solution_key"], field_name="solution_key")
            )
        if len(raw_record_ids) != len(set(raw_record_ids)):
            raise ValueError("accepted_output_payloads must not duplicate record IDs")
        if len(raw_accepted_solution_keys) != len(set(raw_accepted_solution_keys)):
            raise ValueError(
                "accepted_output_payloads cannot share cross-node solution keys"
            )
        accepted_payload_bytes = len(
            _canonical_json_bytes(
                {"accepted_output_payloads": raw_accepted},
                field_name="accepted_output_payloads",
            )
        )
        if accepted_payload_bytes > MAX_ACCEPTED_OUTPUT_PAYLOAD_BYTES:
            raise ValueError(
                "accepted_output_payloads exceeds maximum encoded size "
                f"{MAX_ACCEPTED_OUTPUT_PAYLOAD_BYTES} bytes"
            )
        return cls(
            **{
                **dict(payload),
                "dispatch_envelope": PreparedDispatchEnvelope.from_payload(
                    payload["dispatch_envelope"], catalog=catalog
                ),
                "node_decisions": tuple(
                    PreparedNodeDecision.from_payload(item) for item in raw_decisions
                ),
                "accepted_output_payloads": tuple(
                    AcceptedOutputPayload.from_payload(item, catalog=catalog)
                    for item in raw_accepted
                ),
            }
        )


@dataclass(slots=True, frozen=True)
class InvalidationResult:
    project_id: str
    workspace_id: str
    solution_revision: int
    changed_root_node_ids: tuple[str, ...]
    expired_node_ids: tuple[str, ...]
    removed_node_ids: tuple[str, ...]
    reason_code: str

    def __post_init__(self) -> None:
        for field_name in ("project_id", "workspace_id", "reason_code"):
            object.__setattr__(
                self,
                field_name,
                _text(getattr(self, field_name), field_name=field_name),
            )
        _integer(self.solution_revision, field_name="solution_revision")
        if self.solution_revision < 0:
            raise ValueError("solution_revision must be non-negative")
        object.__setattr__(
            self,
            "changed_root_node_ids",
            _string_tuple(
                self.changed_root_node_ids, field_name="changed_root_node_ids"
            ),
        )
        object.__setattr__(
            self,
            "expired_node_ids",
            _string_tuple(self.expired_node_ids, field_name="expired_node_ids"),
        )
        object.__setattr__(
            self,
            "removed_node_ids",
            _string_tuple(self.removed_node_ids, field_name="removed_node_ids"),
        )

    def _to_payload(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "workspace_id": self.workspace_id,
            "solution_revision": self.solution_revision,
            "changed_root_node_ids": list(self.changed_root_node_ids),
            "expired_node_ids": list(self.expired_node_ids),
            "removed_node_ids": list(self.removed_node_ids),
            "reason_code": self.reason_code,
        }

    def to_payload(self) -> dict[str, Any]:
        return self.from_payload(self._to_payload())._to_payload()

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> InvalidationResult:
        _exact_fields(payload, _INVALIDATION_FIELDS, field_name="invalidation result")
        return cls(**dict(payload))


@dataclass(slots=True, frozen=True)
class SolutionStateChangedEvent:
    project_id: str
    workspace_id: str
    solution_revision: int
    expired_node_ids: tuple[str, ...]
    removed_node_ids: tuple[str, ...]
    reason_code: str
    type: str = "solution_state_changed"

    def __post_init__(self) -> None:
        for field_name in ("project_id", "workspace_id", "reason_code"):
            object.__setattr__(
                self,
                field_name,
                _text(getattr(self, field_name), field_name=field_name),
            )
        _integer(self.solution_revision, field_name="solution_revision")
        if self.solution_revision < 0:
            raise ValueError("solution_revision must be non-negative")
        object.__setattr__(
            self,
            "expired_node_ids",
            _string_tuple(self.expired_node_ids, field_name="expired_node_ids"),
        )
        object.__setattr__(
            self,
            "removed_node_ids",
            _string_tuple(self.removed_node_ids, field_name="removed_node_ids"),
        )
        if self.type != "solution_state_changed":
            raise ValueError("solution state event type must be solution_state_changed")

    @classmethod
    def from_invalidation(cls, result: InvalidationResult) -> SolutionStateChangedEvent:
        if not isinstance(result, InvalidationResult):
            raise TypeError("result must be an InvalidationResult")
        return cls(
            project_id=result.project_id,
            workspace_id=result.workspace_id,
            solution_revision=result.solution_revision,
            expired_node_ids=result.expired_node_ids,
            removed_node_ids=result.removed_node_ids,
            reason_code=result.reason_code,
        )

    def _to_payload(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "project_id": self.project_id,
            "workspace_id": self.workspace_id,
            "solution_revision": self.solution_revision,
            "expired_node_ids": list(self.expired_node_ids),
            "removed_node_ids": list(self.removed_node_ids),
            "reason_code": self.reason_code,
        }

    def to_payload(self) -> dict[str, Any]:
        return self.from_payload(self._to_payload())._to_payload()

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> SolutionStateChangedEvent:
        _exact_fields(
            payload,
            _SOLUTION_STATE_CHANGED_FIELDS,
            field_name="solution state changed event",
        )
        return cls(**dict(payload))


_DISPATCH_FIELDS = frozenset(PreparedDispatchEnvelope.__dataclass_fields__) - {
    "catalog"
}
_DECISION_FIELDS = frozenset(PreparedNodeDecision.__dataclass_fields__)
_ACCEPTED_OUTPUT_FIELDS = frozenset(AcceptedOutputPayload.__dataclass_fields__) - {
    "catalog"
}
_PREPARED_EXECUTION_FIELDS = frozenset(PreparedExecution.__dataclass_fields__)
_INVALIDATION_FIELDS = frozenset(InvalidationResult.__dataclass_fields__)
_SOLUTION_STATE_CHANGED_FIELDS = frozenset(
    SolutionStateChangedEvent.__dataclass_fields__
)

__all__ = [
    "AcceptedOutputPayload",
    "InvalidationResult",
    "MAX_ACCEPTED_NODE_PAYLOADS_PER_PREPARATION",
    "MAX_ACCEPTED_OUTPUT_PAYLOAD_BYTES",
    "MAX_ACCEPTED_PORT_RESULTS_PER_PREPARATION",
    "MAX_PREPARED_NODES",
    "PreparedAction",
    "PreparedDispatchEnvelope",
    "PreparedExecution",
    "PreparedNodeDecision",
    "RecomputeMode",
    "SolutionStateChangedEvent",
    "normalize_trigger_publication_generations",
    "validate_accepted_output_payload",
    "validate_current_output_payload",
]
