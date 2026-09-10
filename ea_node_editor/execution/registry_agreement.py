# Purpose: Own registry, plugin, and add-on agreement payloads and diagnostics.
# Map: subsystems/execution.md
# Tests: tests/test_registry_agreement.py, tests/test_plugin_runtime_agreement.py

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from ea_node_editor.common.clr_type_names import (
    ClrTypeNameError,
    validate_canonical_clr_type_id,
)
from ea_node_editor.common.path_safety import is_reparse_point
from ea_node_editor.nodes.function_plugin import (
    EMPTY_PLUGIN_FINGERPRINT,
    PluginBundleRef,
    PythonFunctionRef,
)
from ea_node_editor.runtime_contracts import DataTypeCatalog
from ea_node_editor.runtime_contracts.data_types import MAX_PAYLOAD_SCHEMA_VERSION
from ea_node_editor.settings import plugin_generations_dir
from ea_node_editor.execution.transport_fields import (
    bool_field as _bool_field,
    nonnegative_int_field as _nonnegative_int_field,
    string_field as _string_field,
)

_CATALOG_FINGERPRINT_LENGTH = 64
_CATALOG_REVISION_RECORD_LIMIT = 4096
_CATALOG_REVISION_IDENTITY_LENGTH = 1024
_CATALOG_REVISION_OWNER_LENGTH = 256
_CATALOG_REVISION_VERSION_LENGTH = 128
_CATALOG_REVISION_KINDS = frozenset({"family", "type", "conversion"})
_CATALOG_DIAGNOSTIC_DIFFERENCE_LIMIT = 8
_CATALOG_DIAGNOSTIC_IDENTITY_LENGTH = 160
_CATALOG_DIAGNOSTIC_MESSAGE_LENGTH = 2048
_PLUGIN_BUNDLE_LIMIT = 128
_PLUGIN_FUNCTION_LIMIT = 4096
_ADDON_RUNTIME_CONFIG_LIMIT = 64
_ADDON_RUNTIME_ID_LIMIT = 128
EMPTY_REGISTRY_CONTRACT_FINGERPRINT = hashlib.sha256(b"").hexdigest()
_PLUGIN_OWNER_LENGTH = 256
_PLUGIN_VERSION_LENGTH = 128
_PLUGIN_PATH_LENGTH = 1024
_PLUGIN_FUNCTION_NAME_LENGTH = 128
_PLUGIN_UNAVAILABLE_REASON_LENGTH = 2048


@dataclass(frozen=True)
class CatalogRevisionRecord:
    kind: Literal["family", "type", "conversion"]
    identity: str
    payload_schema_version: int
    implementation_version: str
    owner_id: str
    owner_version: str
    semantic_digest: str


def _bounded_catalog_text(
    value: object,
    *,
    field_name: str,
    max_length: int,
    allow_empty: bool = False,
) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string.")
    if value != value.strip():
        raise ValueError(f"{field_name} must be a trimmed string.")
    if not allow_empty and not value:
        raise ValueError(f"{field_name} must be non-empty.")
    if len(value) > max_length:
        raise ValueError(f"{field_name} is too long.")
    if any(not character.isprintable() for character in value):
        raise ValueError(f"{field_name} contains control characters.")
    return value


def _sha256_digest(value: object, *, field_name: str) -> str:
    digest = _bounded_catalog_text(
        value,
        field_name=field_name,
        max_length=_CATALOG_FINGERPRINT_LENGTH,
    )
    if len(digest) != _CATALOG_FINGERPRINT_LENGTH or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise ValueError(f"{field_name} must be a 64-character lowercase SHA-256.")
    return digest


def _catalog_fingerprint(value: object) -> str:
    return _sha256_digest(value, field_name="catalog_fingerprint")


def _plugin_fingerprint(value: object) -> str:
    return _sha256_digest(value, field_name="plugin_fingerprint")


def runtime_registry_fingerprint(
    catalog_fingerprint: object,
    plugin_fingerprint: object,
) -> str:
    catalog_digest = _catalog_fingerprint(catalog_fingerprint)
    plugin_digest = _plugin_fingerprint(plugin_fingerprint)
    return hashlib.sha256(
        f"{catalog_digest}:{plugin_digest}".encode("ascii")
    ).hexdigest()


def _python_function_ref_payload(function: PythonFunctionRef) -> dict[str, object]:
    return {
        "bundle_id": function.bundle_id,
        "bundle_digest": function.bundle_digest,
        "module_relative_path": function.module_relative_path,
        "function_name": function.function_name,
        "source_digest": function.source_digest,
        "is_async": function.is_async,
    }


def _python_function_ref(
    value: PythonFunctionRef | Mapping[str, object],
    *,
    index: int,
) -> PythonFunctionRef:
    payload = (
        _python_function_ref_payload(value)
        if isinstance(value, PythonFunctionRef)
        else value
    )
    if not isinstance(payload, Mapping):
        raise ValueError(f"plugin function {index} must be a mapping")
    expected_fields = {
        "bundle_id",
        "bundle_digest",
        "module_relative_path",
        "function_name",
        "source_digest",
        "is_async",
    }
    if set(payload) != expected_fields:
        raise ValueError(f"plugin function {index} has unexpected fields")
    bundle_id = _logical_catalog_identifier(
        _bounded_catalog_text(
            payload["bundle_id"],
            field_name=f"plugin function {index} bundle_id",
            max_length=_PLUGIN_OWNER_LENGTH,
        ),
        field_name=f"plugin function {index} bundle_id",
    )
    module_relative_path = _bounded_catalog_text(
        payload["module_relative_path"],
        field_name=f"plugin function {index} module_relative_path",
        max_length=_PLUGIN_PATH_LENGTH,
    )
    function_name = _bounded_catalog_text(
        payload["function_name"],
        field_name=f"plugin function {index} function_name",
        max_length=_PLUGIN_FUNCTION_NAME_LENGTH,
    )
    is_async = payload["is_async"]
    if not isinstance(is_async, bool):
        raise ValueError(f"plugin function {index} is_async must be a boolean")
    try:
        return PythonFunctionRef(
            bundle_id=bundle_id,
            bundle_digest=_sha256_digest(
                payload["bundle_digest"],
                field_name=f"plugin function {index} bundle_digest",
            ),
            module_relative_path=module_relative_path,
            function_name=function_name,
            source_digest=_sha256_digest(
                payload["source_digest"],
                field_name=f"plugin function {index} source_digest",
            ),
            is_async=is_async,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"plugin function {index} is invalid: {exc}") from exc


def _approved_generation_path(value: object, *, bundle_digest: str) -> str:
    text = _bounded_catalog_text(
        value,
        field_name="approved_generation_root",
        max_length=_PLUGIN_PATH_LENGTH,
    )
    candidate = Path(text)
    if not candidate.is_absolute():
        raise ValueError("approved_generation_root must be absolute")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise ValueError("approved_generation_root does not exist") from exc
    approved_root = plugin_generations_dir().resolve()
    if (
        resolved.parent != approved_root
        or resolved.name != bundle_digest
        or not resolved.is_dir()
        or is_reparse_point(resolved)
    ):
        raise ValueError(
            "approved_generation_root must be a direct immutable generation child"
        )
    return str(resolved)


def _plugin_bundle_ref(
    value: PluginBundleRef | Mapping[str, object],
    *,
    index: int,
    function_offset: int,
) -> PluginBundleRef:
    payload: Mapping[str, object]
    if isinstance(value, PluginBundleRef):
        payload = {
            "owner_id": value.owner_id,
            "version": value.version,
            "generation_id": value.generation_id,
            "bundle_digest": value.bundle_digest,
            "approved_generation_root": value.approved_generation_root,
            "functions": [
                _python_function_ref_payload(item) for item in value.functions
            ],
            "unavailable_reason": value.unavailable_reason,
        }
    elif isinstance(value, Mapping):
        payload = value
    else:
        raise ValueError(f"plugin bundle {index} must be a mapping")
    expected_fields = {
        "owner_id",
        "version",
        "generation_id",
        "bundle_digest",
        "approved_generation_root",
        "functions",
        "unavailable_reason",
    }
    if set(payload) != expected_fields:
        raise ValueError(f"plugin bundle {index} has unexpected fields")
    owner_id = _logical_catalog_identifier(
        _bounded_catalog_text(
            payload["owner_id"],
            field_name=f"plugin bundle {index} owner_id",
            max_length=_PLUGIN_OWNER_LENGTH,
        ),
        field_name=f"plugin bundle {index} owner_id",
    )
    version = _bounded_catalog_text(
        payload["version"],
        field_name=f"plugin bundle {index} version",
        max_length=_PLUGIN_VERSION_LENGTH,
        allow_empty=True,
    )
    generation_id = _sha256_digest(
        payload["generation_id"],
        field_name=f"plugin bundle {index} generation_id",
    )
    bundle_digest = _sha256_digest(
        payload["bundle_digest"],
        field_name=f"plugin bundle {index} bundle_digest",
    )
    raw_functions = payload["functions"]
    if isinstance(raw_functions, (str, bytes)) or not isinstance(
        raw_functions, Sequence
    ):
        raise ValueError(f"plugin bundle {index} functions must be a list")
    if len(raw_functions) > _PLUGIN_FUNCTION_LIMIT - function_offset:
        raise ValueError("plugin_bundles contains too many functions")
    functions = tuple(
        _python_function_ref(item, index=function_offset + offset)
        for offset, item in enumerate(raw_functions)
    )
    unavailable_reason = _bounded_catalog_text(
        payload["unavailable_reason"],
        field_name=f"plugin bundle {index} unavailable_reason",
        max_length=_PLUGIN_UNAVAILABLE_REASON_LENGTH,
        allow_empty=True,
    )
    try:
        return PluginBundleRef(
            owner_id=owner_id,
            version=version,
            generation_id=generation_id,
            bundle_digest=bundle_digest,
            approved_generation_root=_approved_generation_path(
                payload["approved_generation_root"],
                bundle_digest=bundle_digest,
            ),
            functions=functions,
            unavailable_reason=unavailable_reason,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"plugin bundle {index} is invalid: {exc}") from exc


def normalize_plugin_bundle_refs(
    value: object,
) -> tuple[PluginBundleRef, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError("plugin_bundles must be a list")
    if len(value) > _PLUGIN_BUNDLE_LIMIT:
        raise ValueError("plugin_bundles contains too many bundles")
    bundles: list[PluginBundleRef] = []
    function_offset = 0
    for index, item in enumerate(value):
        bundle = _plugin_bundle_ref(
            item,
            index=index,
            function_offset=function_offset,
        )
        function_offset += len(bundle.functions)
        if function_offset > _PLUGIN_FUNCTION_LIMIT:
            raise ValueError("plugin_bundles contains too many functions")
        bundles.append(bundle)
    owners = [bundle.owner_id for bundle in bundles]
    if len(owners) != len(set(owners)):
        raise ValueError("plugin_bundles contains duplicate owner ids")
    functions = [function for bundle in bundles for function in bundle.functions]
    if len(functions) != len(set(functions)):
        raise ValueError("plugin_bundles contains duplicate function refs")
    return tuple(bundles)


def _plugin_bundle_payload(bundle: PluginBundleRef) -> dict[str, object]:
    return {
        "owner_id": bundle.owner_id,
        "version": bundle.version,
        "generation_id": bundle.generation_id,
        "bundle_digest": bundle.bundle_digest,
        "approved_generation_root": bundle.approved_generation_root,
        "functions": [_python_function_ref_payload(item) for item in bundle.functions],
        "unavailable_reason": bundle.unavailable_reason,
    }


def _plugin_agreement(
    plugin_bundles: object,
    plugin_fingerprint: object,
    runtime_fingerprint: object,
    *,
    catalog_fingerprint: str,
) -> tuple[tuple[PluginBundleRef, ...], str, str]:
    bundles = normalize_plugin_bundle_refs(plugin_bundles)
    if not plugin_fingerprint:
        if bundles:
            raise ValueError(
                "plugin_fingerprint is required when plugin_bundles is non-empty"
            )
        plugin_digest = EMPTY_PLUGIN_FINGERPRINT
    else:
        plugin_digest = _plugin_fingerprint(plugin_fingerprint)
    expected_runtime = runtime_registry_fingerprint(
        catalog_fingerprint,
        plugin_digest,
    )
    if runtime_fingerprint:
        supplied_runtime = _sha256_digest(
            runtime_fingerprint,
            field_name="runtime_registry_fingerprint",
        )
        if supplied_runtime != expected_runtime:
            raise ValueError(
                "runtime_registry_fingerprint does not match catalog and plugin fingerprints"
            )
    return bundles, plugin_digest, expected_runtime


def _logical_catalog_identifier(value: str, *, field_name: str) -> str:
    if len(value) >= 2 and value[0].isalpha() and value[1] == ":":
        raise ValueError(f"{field_name} must be a path-free logical identifier.")
    if any(not (character.isalnum() or character in "._:@+-") for character in value):
        raise ValueError(f"{field_name} must be a path-free logical identifier.")
    return value


def normalize_addon_runtime_config(
    value: object,
) -> tuple[tuple[str, bool], ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError("addon_runtime_config must be a list")
    if len(value) > _ADDON_RUNTIME_CONFIG_LIMIT:
        raise ValueError("addon_runtime_config contains too many entries")
    normalized: dict[str, bool] = {}
    for index, raw_entry in enumerate(value):
        if isinstance(raw_entry, Mapping):
            if set(raw_entry) != {"addon_id", "enabled"}:
                raise ValueError(
                    f"addon_runtime_config[{index}] must contain addon_id and enabled"
                )
            raw_addon_id = raw_entry["addon_id"]
            enabled = raw_entry["enabled"]
        elif (
            isinstance(raw_entry, Sequence)
            and not isinstance(raw_entry, (str, bytes))
            and len(raw_entry) == 2
        ):
            raw_addon_id, enabled = raw_entry
        else:
            raise ValueError(f"addon_runtime_config[{index}] must be an add-on state")
        if not isinstance(raw_addon_id, str):
            raise ValueError(f"addon_runtime_config[{index}].addon_id must be a string")
        addon_id = raw_addon_id.strip()
        if not addon_id or len(addon_id) > _ADDON_RUNTIME_ID_LIMIT:
            raise ValueError(
                f"addon_runtime_config[{index}].addon_id must be 1 to "
                f"{_ADDON_RUNTIME_ID_LIMIT} characters"
            )
        _logical_catalog_identifier(
            addon_id,
            field_name=f"addon_runtime_config[{index}].addon_id",
        )
        if type(enabled) is not bool:
            raise ValueError(f"addon_runtime_config[{index}].enabled must be a boolean")
        if addon_id in normalized:
            raise ValueError("addon_runtime_config contains duplicate add-on ids")
        normalized[addon_id] = enabled
    return tuple(sorted(normalized.items()))


def _addon_runtime_config_payload(
    value: tuple[tuple[str, bool], ...],
) -> list[dict[str, object]]:
    return [
        {"addon_id": addon_id, "enabled": enabled}
        for addon_id, enabled in normalize_addon_runtime_config(value)
    ]


def _canonical_catalog_type_id(value: str, *, field_name: str) -> str:
    try:
        validate_canonical_clr_type_id(value)
    except ClrTypeNameError as exc:
        raise ValueError(f"{field_name} must be a canonical CLR type ID.") from exc
    return value


def _catalog_revision_identity(
    value: object,
    *,
    kind: str,
    field_name: str,
) -> str:
    identity = _bounded_catalog_text(
        value,
        field_name=field_name,
        max_length=_CATALOG_REVISION_IDENTITY_LENGTH,
    )
    if kind == "family":
        return _logical_catalog_identifier(identity, field_name=field_name)
    if kind == "type":
        return _canonical_catalog_type_id(identity, field_name=field_name)
    endpoints = identity.split(" -> ")
    if len(endpoints) != 2 or not all(endpoints):
        raise ValueError(f"{field_name} must contain two canonical CLR type IDs.")
    for endpoint in endpoints:
        _canonical_catalog_type_id(endpoint, field_name=field_name)
    return identity


def _catalog_revision_record(
    value: CatalogRevisionRecord | Mapping[str, object],
    *,
    index: int,
) -> CatalogRevisionRecord:
    if isinstance(value, CatalogRevisionRecord):
        payload: Mapping[str, object] = {
            "kind": value.kind,
            "identity": value.identity,
            "payload_schema_version": value.payload_schema_version,
            "implementation_version": value.implementation_version,
            "owner_id": value.owner_id,
            "owner_version": value.owner_version,
            "semantic_digest": value.semantic_digest,
        }
    elif isinstance(value, Mapping):
        payload = value
    else:
        raise ValueError(f"catalog_revisions[{index}] must be a mapping.")
    expected_fields = {
        "kind",
        "identity",
        "payload_schema_version",
        "implementation_version",
        "owner_id",
        "owner_version",
        "semantic_digest",
    }
    if set(payload) != expected_fields:
        raise ValueError(
            f"catalog_revisions[{index}] must contain exactly "
            f"{sorted(expected_fields)!r}."
        )
    kind = _bounded_catalog_text(
        payload["kind"],
        field_name=f"catalog_revisions[{index}].kind",
        max_length=16,
    )
    if kind not in _CATALOG_REVISION_KINDS:
        raise ValueError(f"catalog_revisions[{index}].kind is invalid.")
    schema_version = payload["payload_schema_version"]
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version < 0
        or schema_version > MAX_PAYLOAD_SCHEMA_VERSION
        or (kind == "type" and schema_version == 0)
        or (kind in {"family", "conversion"} and schema_version != 0)
    ):
        raise ValueError(
            f"catalog_revisions[{index}].payload_schema_version is invalid."
        )
    return CatalogRevisionRecord(
        kind=kind,  # type: ignore[arg-type]
        identity=_catalog_revision_identity(
            payload["identity"],
            kind=kind,
            field_name=f"catalog_revisions[{index}].identity",
        ),
        payload_schema_version=schema_version,
        implementation_version=_logical_catalog_identifier(
            _bounded_catalog_text(
                payload["implementation_version"],
                field_name=f"catalog_revisions[{index}].implementation_version",
                max_length=_CATALOG_REVISION_VERSION_LENGTH,
                allow_empty=kind == "family",
            ),
            field_name=f"catalog_revisions[{index}].implementation_version",
        ),
        owner_id=_logical_catalog_identifier(
            _bounded_catalog_text(
                payload["owner_id"],
                field_name=f"catalog_revisions[{index}].owner_id",
                max_length=_CATALOG_REVISION_OWNER_LENGTH,
            ),
            field_name=f"catalog_revisions[{index}].owner_id",
        ),
        owner_version=_logical_catalog_identifier(
            _bounded_catalog_text(
                payload["owner_version"],
                field_name=f"catalog_revisions[{index}].owner_version",
                max_length=_CATALOG_REVISION_VERSION_LENGTH,
                allow_empty=True,
            ),
            field_name=f"catalog_revisions[{index}].owner_version",
        ),
        semantic_digest=_sha256_digest(
            payload["semantic_digest"],
            field_name=f"catalog_revisions[{index}].semantic_digest",
        ),
    )


def normalize_catalog_revisions(value: object) -> tuple[CatalogRevisionRecord, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("catalog_revisions must be a list.")
    if len(value) > _CATALOG_REVISION_RECORD_LIMIT:
        raise ValueError("catalog_revisions contains too many records.")
    records = tuple(
        _catalog_revision_record(item, index=index) for index, item in enumerate(value)
    )
    if records != tuple(
        sorted(
            records,
            key=lambda record: (
                record.kind,
                record.identity,
                record.payload_schema_version,
                record.implementation_version,
                record.owner_id,
                record.owner_version,
                record.semantic_digest,
            ),
        )
    ):
        raise ValueError("catalog_revisions must be deterministically sorted.")
    identities = [(record.kind, record.identity) for record in records]
    if len(identities) != len(set(identities)):
        raise ValueError("catalog_revisions contains duplicate identities.")
    return records


def catalog_revision_records(
    catalog: DataTypeCatalog,
) -> tuple[CatalogRevisionRecord, ...]:
    if not isinstance(catalog, DataTypeCatalog) or not catalog.is_frozen:
        raise ValueError("catalog agreement requires a frozen data-type catalog.")
    records: list[CatalogRevisionRecord] = []
    for snapshot_record in catalog.snapshot():
        kind = snapshot_record.get("kind")
        semantic_digest = _catalog_snapshot_record_digest(snapshot_record)
        if kind == "family":
            records.append(
                CatalogRevisionRecord(
                    kind="family",
                    identity=str(snapshot_record["family_id"]),
                    payload_schema_version=0,
                    implementation_version="",
                    owner_id=str(snapshot_record["owner_id"]),
                    owner_version=str(snapshot_record["owner_version"]),
                    semantic_digest=semantic_digest,
                )
            )
        elif kind == "type":
            records.append(
                CatalogRevisionRecord(
                    kind="type",
                    identity=str(snapshot_record["type_id"]),
                    payload_schema_version=int(
                        snapshot_record["payload_schema_version"]
                    ),
                    implementation_version=str(
                        snapshot_record["implementation_version"]
                    ),
                    owner_id=str(snapshot_record["owner_id"]),
                    owner_version=str(snapshot_record["owner_version"]),
                    semantic_digest=semantic_digest,
                )
            )
        elif kind == "conversion":
            records.append(
                CatalogRevisionRecord(
                    kind="conversion",
                    identity=(
                        f"{snapshot_record['source_type_id']} -> "
                        f"{snapshot_record['target_type_id']}"
                    ),
                    payload_schema_version=0,
                    implementation_version=str(
                        snapshot_record["implementation_version"]
                    ),
                    owner_id=str(snapshot_record["owner_id"]),
                    owner_version=str(snapshot_record["owner_version"]),
                    semantic_digest=semantic_digest,
                )
            )
    return normalize_catalog_revisions(
        sorted(
            records,
            key=lambda record: (
                record.kind,
                record.identity,
                record.payload_schema_version,
                record.implementation_version,
                record.owner_id,
                record.owner_version,
                record.semantic_digest,
            ),
        )
    )


def _catalog_snapshot_record_digest(
    snapshot_record: Mapping[str, object],
) -> str:
    semantic_record = {
        str(key): value
        for key, value in snapshot_record.items()
        if key != "source_label"
    }
    payload = json.dumps(
        semantic_record,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def catalog_agreement(
    catalog: DataTypeCatalog,
) -> tuple[str, tuple[CatalogRevisionRecord, ...]]:
    return _catalog_fingerprint(catalog.fingerprint()), catalog_revision_records(
        catalog
    )


def catalog_agreement_from_payload(
    payload: Mapping[str, object],
) -> tuple[str, tuple[CatalogRevisionRecord, ...]]:
    if "catalog_fingerprint" not in payload or "catalog_revisions" not in payload:
        raise ValueError(
            "start_run requires catalog_fingerprint and catalog_revisions."
        )
    return (
        _catalog_fingerprint(payload["catalog_fingerprint"]),
        normalize_catalog_revisions(payload["catalog_revisions"]),
    )


def _catalog_revision_payload(
    record: CatalogRevisionRecord,
) -> dict[str, object]:
    normalized = _catalog_revision_record(record, index=0)
    return {
        "kind": normalized.kind,
        "identity": normalized.identity,
        "payload_schema_version": normalized.payload_schema_version,
        "implementation_version": normalized.implementation_version,
        "owner_id": normalized.owner_id,
        "owner_version": normalized.owner_version,
        "semantic_digest": normalized.semantic_digest,
    }


def catalog_mismatch_message(
    expected_fingerprint: str,
    expected_revisions: object,
    worker_catalog: DataTypeCatalog,
) -> str:
    expected_fingerprint = _catalog_fingerprint(expected_fingerprint)
    expected_records = normalize_catalog_revisions(expected_revisions)
    worker_fingerprint, worker_records = catalog_agreement(worker_catalog)
    if expected_fingerprint == worker_fingerprint:
        return ""

    expected_by_identity = {
        (record.kind, record.identity): record for record in expected_records
    }
    worker_by_identity = {
        (record.kind, record.identity): record for record in worker_records
    }
    changed_keys = [
        key
        for key in sorted(set(expected_by_identity) | set(worker_by_identity))
        if expected_by_identity.get(key) != worker_by_identity.get(key)
    ]
    details: list[str] = []
    for key in changed_keys[:_CATALOG_DIAGNOSTIC_DIFFERENCE_LIMIT]:
        desktop = expected_by_identity.get(key)
        worker = worker_by_identity.get(key)
        if worker is None:
            details.append(f"{_trusted_catalog_revision_label(desktop)}: desktop-only")
            continue
        label = _trusted_catalog_revision_label(worker)
        if desktop is None:
            details.append(f"{label}: worker-only")
            continue
        details.append(
            f"{label}: desktop digest={desktop.semantic_digest[:12]}, "
            f"worker digest={worker.semantic_digest[:12]}"
        )
    if len(changed_keys) > _CATALOG_DIAGNOSTIC_DIFFERENCE_LIMIT:
        details.append(
            f"{len(changed_keys) - _CATALOG_DIAGNOSTIC_DIFFERENCE_LIMIT} "
            "more differences"
        )
    if not details:
        details.append("compact semantic records agree; other catalog metadata differs")
    message_prefix = (
        "Data-type catalog mismatch before execution: "
        f"desktop={expected_fingerprint}, worker={worker_fingerprint}. "
    )
    return _bounded_catalog_mismatch_message(
        message_prefix,
        details,
        total_differences=len(changed_keys),
    )


def _bounded_catalog_mismatch_message(
    prefix: str,
    details: list[str],
    *,
    total_differences: int,
) -> str:
    message = prefix + "; ".join(details)
    if len(message) <= _CATALOG_DIAGNOSTIC_MESSAGE_LENGTH:
        return message

    kept_details = list(details)
    while kept_details:
        kept_details.pop()
        shown = min(
            len(kept_details),
            total_differences,
            _CATALOG_DIAGNOSTIC_DIFFERENCE_LIMIT,
        )
        marker = (
            "[catalog mismatch details truncated: "
            f"showing {shown} of {total_differences} differences]"
        )
        message = prefix + "; ".join((*kept_details, marker))
        if len(message) <= _CATALOG_DIAGNOSTIC_MESSAGE_LENGTH:
            return message

    marker = (
        "[catalog mismatch details truncated: "
        f"showing 0 of {total_differences} differences]"
    )
    return prefix + marker


def _trusted_catalog_revision_label(record: CatalogRevisionRecord) -> str:
    identity = record.identity
    if len(identity) > _CATALOG_DIAGNOSTIC_IDENTITY_LENGTH:
        digest_tag = f"#{record.semantic_digest[:12]}"
        readable_length = (
            _CATALOG_DIAGNOSTIC_IDENTITY_LENGTH - len("...") - len(digest_tag)
        )
        prefix_length = (readable_length * 2) // 3
        suffix_length = readable_length - prefix_length
        identity = (
            f"{identity[:prefix_length]}...{identity[-suffix_length:]}{digest_tag}"
        )
    revisions = [f"owner={record.owner_id}"]
    if record.payload_schema_version:
        revisions.insert(0, f"schema={record.payload_schema_version}")
    return f"{record.kind} {identity} ({', '.join(revisions)})"


__all__ = [
    "CatalogRevisionRecord",
    "EMPTY_REGISTRY_CONTRACT_FINGERPRINT",
    "catalog_agreement",
    "catalog_agreement_from_payload",
    "catalog_mismatch_message",
    "catalog_revision_records",
    "normalize_addon_runtime_config",
    "normalize_catalog_revisions",
    "normalize_plugin_bundle_refs",
    "runtime_registry_fingerprint",
]
