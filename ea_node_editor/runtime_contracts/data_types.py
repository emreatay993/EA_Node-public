# Purpose: Define the dependency-light semantic data-type catalog and compatibility rules.
# Map: subsystems/supporting_runtime_assets.md
# Tests: tests/test_data_type_catalog.py

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from types import MappingProxyType
from typing import Callable, Iterable, Literal, Mapping

from ea_node_editor.common.clr_type_names import (
    ClrTypeNameError,
    validate_canonical_clr_type_id,
)

TypeCarrierKind = Literal["native", "inline", "handle", "artifact"]
TypePersistence = Literal["never", "inline", "saved_artifact"]
TypeSensitivity = Literal["normal", "sensitive", "secret"]
CompatibilityStatus = Literal[
    "assignable",
    "convertible",
    "runtime_check",
    "incompatible",
    "unresolved",
]

GRAPH_DATA_TYPE_ID = "COREX.DataTypes.Any"
JSON_VALUE_DATA_TYPE_ID = "COREX.DataTypes.JsonValue"
BOOLEAN_DATA_TYPE_ID = "COREX.DataTypes.Bool"
INTEGER_DATA_TYPE_ID = "COREX.DataTypes.Int"
DOUBLE_DATA_TYPE_ID = "COREX.DataTypes.Double"
STRING_DATA_TYPE_ID = "COREX.DataTypes.String"
GRAPH_DICTIONARY_DATA_TYPE_ID = "COREX.DataTypes.GraphDictionary"
GRAPH_ARRAY_DATA_TYPE_ID = "COREX.DataTypes.GraphArray"
INTERVAL_1D_GRAPH_DATA_TYPE_ID = "COREX.DataTypes.Interval1D"
PATH_DATA_TYPE_ID = "COREX.DataTypes.Path"
JSON_DATA_TYPE_ID = "COREX.DataTypes.Json"
STRING_LIST_DATA_TYPE_ID = "COREX.DataTypes.StringList"
ARRAY_DATA_REF_TYPE_ID = "COREX.Runtime.ArrayDataRef"
ARRAY_SLICE_2D_REF_TYPE_ID = "COREX.Runtime.ArraySlice2DRef"
TABULAR_DATA_REF_TYPE_ID = "COREX.Runtime.TabularDataRef"
TABULAR_WINDOW_REF_TYPE_ID = "COREX.Runtime.TabularWindowRef"
ENGINEERING_SCENE_DATA_TYPE_ID = "COREX.Engineering.Scene"
ENGINEERING_SELECTION_SET_DATA_TYPE_ID = "COREX.Engineering.SelectionSet"
VIEWER_SESSION_DATA_TYPE_ID = "COREX.Viewer.Session"
PLOT_EXPORT_BUNDLE_DATA_TYPE_ID = "COREX.Plot.ExportBundle"
COREX_VIEWER_SESSION_HANDLE_KIND = "corex.viewer_session"
CONNECTION_FALLBACK_CAPABILITY = "connection_fallback"
MAX_PAYLOAD_SCHEMA_VERSION = 2_147_483_647

_CARRIER_KINDS = frozenset({"native", "inline", "handle", "artifact"})
_PERSISTENCE_KINDS = frozenset({"never", "inline", "saved_artifact"})
_SENSITIVITY_KINDS = frozenset({"normal", "sensitive", "secret"})
_CATALOG_OWNER_ID_LENGTH = 256
_CATALOG_VERSION_LENGTH = 128


class DataTypeCatalogError(ValueError):
    """Raised when a catalog declaration or value violates its contract."""


@dataclass(frozen=True, slots=True)
class DataTypeFamilySpec:
    family_id: str
    display_name: str
    color_token: str
    icon_key: str


@dataclass(frozen=True, slots=True)
class DataTypeSpec:
    type_id: str
    display_name: str
    family_id: str
    validate_item: Callable[[object], bool]
    coerce_untyped_input: Callable[[object], object] | None = None
    description: str = ""
    parents: tuple[str, ...] = ()
    abstract: bool = False
    carriers: frozenset[TypeCarrierKind] = frozenset({"native"})
    persistence: TypePersistence = "never"
    sensitivity: TypeSensitivity = "normal"
    capabilities: frozenset[str] = frozenset()
    payload_schema_version: int = 1
    implementation_version: str = "1"


@dataclass(frozen=True, slots=True)
class DataConversionSpec:
    source_type_id: str
    target_type_id: str
    convert_item: Callable[[object], object]
    implementation_version: str = "1"


@dataclass(frozen=True, slots=True)
class DataTypeCompatibility:
    status: CompatibilityStatus
    source_type_id: str
    target_type_id: str
    matched_type_id: str = ""
    reason_code: str = ""

    @property
    def is_compatible(self) -> bool:
        return self.status in {"assignable", "convertible", "runtime_check"}


@dataclass(frozen=True, slots=True)
class _Provenance:
    owner_id: str
    owner_version: str
    source_label: str


class DataTypeCatalog:
    """Instance-owned semantic type declarations, relations, and conversions."""

    def __init__(self) -> None:
        self._families: dict[str, DataTypeFamilySpec] = {}
        self._types: dict[str, DataTypeSpec] = {}
        self._conversions: dict[tuple[str, str], DataConversionSpec] = {}
        self._family_provenance: dict[str, _Provenance] = {}
        self._type_provenance: dict[str, _Provenance] = {}
        self._conversion_provenance: dict[tuple[str, str], _Provenance] = {}
        self._ancestors: dict[str, frozenset[str]] = {}
        self._frozen = False

    def register_many(
        self,
        *,
        families: Iterable[DataTypeFamilySpec] = (),
        types: Iterable[DataTypeSpec] = (),
        conversions: Iterable[DataConversionSpec] = (),
        owner_id: str,
        owner_version: str = "",
        source_label: str = "",
    ) -> None:
        if self._frozen:
            raise DataTypeCatalogError("catalog is frozen")

        provenance = _validate_provenance(owner_id, owner_version, source_label)
        family_items = tuple(families)
        type_items = tuple(types)
        conversion_items = tuple(conversions)

        staged_families = dict(self._families)
        staged_types = dict(self._types)
        staged_conversions = dict(self._conversions)
        staged_family_provenance = dict(self._family_provenance)
        staged_type_provenance = dict(self._type_provenance)
        staged_conversion_provenance = dict(self._conversion_provenance)

        for family in family_items:
            _validate_family(family)
            if family.family_id in staged_families:
                raise DataTypeCatalogError(
                    f"duplicate data-type family ID {family.family_id!r}"
                )
            staged_families[family.family_id] = family
            staged_family_provenance[family.family_id] = provenance

        for spec in type_items:
            _validate_type_spec(spec)
            if spec.type_id in staged_types:
                raise DataTypeCatalogError(f"duplicate data-type ID {spec.type_id!r}")
            staged_types[spec.type_id] = spec
            staged_type_provenance[spec.type_id] = provenance

        for conversion in conversion_items:
            _validate_conversion(conversion)
            key = (conversion.source_type_id, conversion.target_type_id)
            if key in staged_conversions:
                raise DataTypeCatalogError(
                    "duplicate data conversion "
                    f"{conversion.source_type_id!r} -> {conversion.target_type_id!r}"
                )
            missing_endpoint = next(
                (
                    type_id
                    for type_id in key
                    if type_id not in staged_types
                ),
                None,
            )
            if missing_endpoint is not None:
                raise DataTypeCatalogError(
                    "conversion "
                    f"{conversion.source_type_id!r} -> "
                    f"{conversion.target_type_id!r} references unknown endpoint "
                    f"{missing_endpoint!r}"
                )
            staged_conversions[key] = conversion
            staged_conversion_provenance[key] = provenance

        ancestors = _validate_catalog_integrity(
            families=staged_families,
            types=staged_types,
            conversions=staged_conversions,
        )

        self._families = staged_families
        self._types = staged_types
        self._conversions = staged_conversions
        self._family_provenance = staged_family_provenance
        self._type_provenance = staged_type_provenance
        self._conversion_provenance = staged_conversion_provenance
        self._ancestors = ancestors

    def freeze(self) -> None:
        if not self._frozen:
            self._ancestors = _validate_catalog_integrity(
                families=self._families,
                types=self._types,
                conversions=self._conversions,
            )
            self._frozen = True

    @property
    def is_frozen(self) -> bool:
        return self._frozen

    def fork(self, *, excluding_owner_id: str = "") -> DataTypeCatalog:
        """Return a mutable staging copy, optionally without one owner's records."""
        if excluding_owner_id:
            _validate_catalog_identifier(
                excluding_owner_id,
                "excluded owner ID",
                max_length=_CATALOG_OWNER_ID_LENGTH,
            )

        forked = DataTypeCatalog()
        forked._families = {
            family_id: family
            for family_id, family in self._families.items()
            if not excluding_owner_id
            or self._family_provenance[family_id].owner_id != excluding_owner_id
        }
        forked._types = {
            type_id: spec
            for type_id, spec in self._types.items()
            if not excluding_owner_id
            or self._type_provenance[type_id].owner_id != excluding_owner_id
        }
        forked._conversions = {
            key: conversion
            for key, conversion in self._conversions.items()
            if not excluding_owner_id
            or self._conversion_provenance[key].owner_id != excluding_owner_id
        }
        forked._family_provenance = {
            family_id: provenance
            for family_id, provenance in self._family_provenance.items()
            if family_id in forked._families
        }
        forked._type_provenance = {
            type_id: provenance
            for type_id, provenance in self._type_provenance.items()
            if type_id in forked._types
        }
        forked._conversion_provenance = {
            key: provenance
            for key, provenance in self._conversion_provenance.items()
            if key in forked._conversions
        }
        if not excluding_owner_id:
            forked._ancestors = dict(self._ancestors)
        return forked

    def require(self, type_id: str) -> DataTypeSpec:
        spec = self.get(type_id)
        if spec is None:
            raise DataTypeCatalogError(f"unknown data-type ID {type_id!r}")
        return spec

    def get(self, type_id: str) -> DataTypeSpec | None:
        return self._types.get(type_id)

    def all_specs(self) -> tuple[DataTypeSpec, ...]:
        return tuple(self._types[type_id] for type_id in sorted(self._types))

    def owner_of(self, type_id: str) -> str:
        self.require(type_id)
        return self._type_provenance[type_id].owner_id

    def is_assignable(self, source_type_id: str, target_type_id: str) -> bool:
        if source_type_id not in self._types or target_type_id not in self._types:
            return False
        return (
            source_type_id == target_type_id
            or target_type_id in self._ancestors[source_type_id]
        )

    def compatibility(
        self,
        source_type_id: str,
        target_type_id: str,
        accepted_type_ids: Iterable[str] = (),
    ) -> DataTypeCompatibility:
        if source_type_id not in self._types:
            return DataTypeCompatibility(
                status="unresolved",
                source_type_id=source_type_id,
                target_type_id=target_type_id,
                reason_code="unknown_source",
            )

        best: tuple[int, DataTypeCompatibility] | None = None
        for candidate_id in (target_type_id, *tuple(accepted_type_ids)):
            target = self._types.get(candidate_id)
            if target is None:
                candidate = DataTypeCompatibility(
                    status="unresolved",
                    source_type_id=source_type_id,
                    target_type_id=target_type_id,
                    matched_type_id=candidate_id,
                    reason_code="unknown_target",
                )
                rank = 4
            elif self.is_assignable(source_type_id, candidate_id):
                exact = source_type_id == candidate_id
                candidate = DataTypeCompatibility(
                    status="assignable",
                    source_type_id=source_type_id,
                    target_type_id=target_type_id,
                    matched_type_id=candidate_id,
                    reason_code="exact" if exact else "declared_parent",
                )
                rank = 0 if exact else 1
            elif (source_type_id, candidate_id) in self._conversions:
                candidate = DataTypeCompatibility(
                    status="convertible",
                    source_type_id=source_type_id,
                    target_type_id=target_type_id,
                    matched_type_id=candidate_id,
                    reason_code="direct_conversion",
                )
                rank = 2
            elif self._types[source_type_id].abstract and self.is_assignable(
                candidate_id, source_type_id
            ):
                candidate = DataTypeCompatibility(
                    status="runtime_check",
                    source_type_id=source_type_id,
                    target_type_id=target_type_id,
                    matched_type_id=candidate_id,
                    reason_code="abstract_source_descendant",
                )
                rank = 3
            else:
                candidate = DataTypeCompatibility(
                    status="incompatible",
                    source_type_id=source_type_id,
                    target_type_id=target_type_id,
                    reason_code="no_declared_relation",
                )
                rank = 5

            if best is None or rank < best[0]:
                best = (rank, candidate)
                if rank == 0:
                    break

        if best is not None:
            return best[1]
        return DataTypeCompatibility(
            status="incompatible",
            source_type_id=source_type_id,
            target_type_id=target_type_id,
            reason_code="no_declared_relation",
        )

    def prepare_untyped_input(self, target_type_id: str, value: object) -> object:
        spec = self.require(target_type_id)
        if value is None or _validator_accepts(spec, value):
            return value
        if spec.coerce_untyped_input is None:
            raise DataTypeCatalogError(
                f"value is invalid for data type {target_type_id!r} and no "
                "untyped coercer is registered"
            )
        try:
            coerced = spec.coerce_untyped_input(value)
        except Exception as exc:
            raise DataTypeCatalogError(
                f"untyped coercion failed for data type {target_type_id!r}: {exc}"
            ) from exc
        if coerced is None or _validator_accepts(spec, coerced):
            return coerced
        raise DataTypeCatalogError(
            f"untyped coercion produced an invalid value for data type "
            f"{target_type_id!r}"
        )

    def convert_typed_input(
        self,
        source_type_id: str,
        target_type_id: str,
        value: object,
    ) -> object:
        self.require(source_type_id)
        self.require(target_type_id)
        if value is None:
            return None

        compatibility = self.compatibility(source_type_id, target_type_id)
        if compatibility.status == "assignable":
            return value
        if compatibility.status == "runtime_check":
            if _validator_accepts(self._types[target_type_id], value):
                return value
            raise DataTypeCatalogError(
                f"runtime value from abstract type {source_type_id!r} does not "
                f"satisfy target {target_type_id!r}"
            )
        if compatibility.status != "convertible":
            raise DataTypeCatalogError(
                f"data type {source_type_id!r} is not convertible to "
                f"{target_type_id!r}: {compatibility.reason_code}"
            )

        conversion = self._conversions[(source_type_id, target_type_id)]
        try:
            converted = conversion.convert_item(value)
        except Exception as exc:
            raise DataTypeCatalogError(
                f"conversion {source_type_id!r} -> {target_type_id!r} failed: {exc}"
            ) from exc
        self.validate_output(target_type_id, converted)
        return converted

    def validate_output(self, declared_type_id: str, value: object) -> None:
        spec = self.require(declared_type_id)
        if value is None:
            return
        candidates = (
            (
                spec,
                *tuple(
                    candidate
                    for candidate in self.all_specs()
                    if not candidate.abstract
                    and self.is_assignable(candidate.type_id, declared_type_id)
                ),
            )
            if spec.abstract
            else (spec,)
        )
        validator_errors: list[str] = []
        for candidate in candidates:
            try:
                if _validator_accepts(candidate, value):
                    return
            except DataTypeCatalogError as exc:
                validator_errors.append(str(exc))
        detail = (
            f"; descendant validator errors: {'; '.join(validator_errors)}"
            if validator_errors
            else ""
        )
        raise DataTypeCatalogError(
            f"output value is invalid for declared data type "
            f"{declared_type_id!r}{detail}"
        )

    def validate_carrier(self, declared_type_id: str, value: object) -> None:
        """Validate semantic identity, carrier, schema, relation, and payload."""

        from ea_node_editor.runtime_contracts.data_tree import DataTree
        from ea_node_editor.runtime_contracts.scientific_values import ArrayValue, TableValue
        from ea_node_editor.runtime_contracts.interval_1d import Interval1D
        from ea_node_editor.runtime_contracts.image_value import ImageValue
        from ea_node_editor.runtime_contracts.value_refs import (
            RuntimeArtifactRef,
            RuntimeHandleRef,
            TypedInlineValue,
        )
        from ea_node_editor.runtime_contracts.tabular_data import (
            ArrayDataRef,
            ArraySlice2DRef,
            TabularDataRef,
            TabularWindowRef,
        )

        declared_spec = self.require(declared_type_id)
        if value is None:
            return
        if isinstance(value, DataTree):
            for _path, items in value.branches:
                for item in items:
                    self.validate_carrier(declared_type_id, item)
            return

        actual_type_id = declared_type_id
        carrier: TypeCarrierKind = "native"
        schema_version: int | None = None
        validated_value = value
        explicit_semantic_identity = False

        if isinstance(value, (ArrayValue, TableValue)):
            explicit_semantic_identity = True
            actual_type_id = value.data_type_id
            schema_version = 1
        elif isinstance(value, TypedInlineValue):
            explicit_semantic_identity = True
            actual_type_id = value.data_type_id
            carrier = "inline"
            schema_version = value.schema_version
            validated_value = value.payload
        elif isinstance(value, ImageValue):
            explicit_semantic_identity = True
            actual_type_id = value.data_type_id
            carrier = "inline"
            schema_version = value.schema_version
        elif isinstance(value, RuntimeHandleRef):
            explicit_semantic_identity = True
            actual_type_id = value.data_type_id
            carrier = "handle"
            schema_version = value.schema_version
        elif isinstance(value, RuntimeArtifactRef):
            explicit_semantic_identity = True
            actual_type_id = value.data_type_id
            carrier = "artifact"
            schema_version = value.schema_version
        elif isinstance(value, TabularDataRef):
            actual_type_id = TABULAR_DATA_REF_TYPE_ID
            carrier = "handle"
            schema_version = 1
        elif isinstance(value, ArrayDataRef):
            actual_type_id = ARRAY_DATA_REF_TYPE_ID
            carrier = "handle"
            schema_version = 1
        elif isinstance(value, TabularWindowRef):
            actual_type_id = TABULAR_WINDOW_REF_TYPE_ID
            carrier = "handle"
            schema_version = 1
        elif isinstance(value, ArraySlice2DRef):
            actual_type_id = ARRAY_SLICE_2D_REF_TYPE_ID
            carrier = "handle"
            schema_version = 1
        elif isinstance(value, Interval1D):
            actual_type_id = INTERVAL_1D_GRAPH_DATA_TYPE_ID
            carrier = "inline"
            schema_version = 1

        actual_spec = self.require(actual_type_id)
        if (
            isinstance(value, RuntimeHandleRef)
            and value.metadata
            and (
                actual_spec.sensitivity == "secret"
                or declared_spec.sensitivity == "secret"
            )
        ):
            raise DataTypeCatalogError("secret runtime handle metadata must be empty")
        if explicit_semantic_identity and actual_spec.abstract:
            raise DataTypeCatalogError(
                f"semantic runtime carrier data type {actual_type_id!r} "
                "must be concrete"
            )
        if carrier not in actual_spec.carriers:
            raise DataTypeCatalogError(
                f"data type {actual_type_id!r} does not allow {carrier!r} carriers"
            )
        if (
            schema_version is not None
            and schema_version != actual_spec.payload_schema_version
        ):
            raise DataTypeCatalogError(
                f"carrier schema version {schema_version} does not match "
                f"{actual_type_id!r} schema {actual_spec.payload_schema_version}"
            )
        if not self.is_assignable(actual_type_id, declared_type_id):
            raise DataTypeCatalogError(
                f"carrier data type {actual_type_id!r} is not assignable to "
                f"declared data type {declared_type_id!r}"
            )
        if carrier not in declared_spec.carriers:
            raise DataTypeCatalogError(
                f"declared data type {declared_type_id!r} does not allow "
                f"{carrier!r} carriers"
            )
        self.validate_output(actual_type_id, validated_value)

    def fingerprint(self) -> str:
        semantic_records = tuple(
            {
                key: value
                for key, value in record.items()
                if key != "source_label"
            }
            for record in self._snapshot_records()
        )
        payload = json.dumps(
            semantic_records,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def snapshot(self) -> tuple[Mapping[str, object], ...]:
        return tuple(
            MappingProxyType(dict(record)) for record in self._snapshot_records()
        )

    def _snapshot_records(self) -> tuple[dict[str, object], ...]:
        records: list[dict[str, object]] = []
        for family_id in sorted(self._families):
            family = self._families[family_id]
            records.append(
                {
                    "kind": "family",
                    "family_id": family.family_id,
                    "display_name": family.display_name,
                    "color_token": family.color_token,
                    "icon_key": family.icon_key,
                    **_provenance_record(self._family_provenance[family_id]),
                }
            )
        for type_id in sorted(self._types):
            spec = self._types[type_id]
            records.append(
                {
                    "kind": "type",
                    "type_id": spec.type_id,
                    "display_name": spec.display_name,
                    "family_id": spec.family_id,
                    "description": spec.description,
                    "parents": tuple(sorted(spec.parents)),
                    "abstract": spec.abstract,
                    "carriers": tuple(sorted(spec.carriers)),
                    "persistence": spec.persistence,
                    "sensitivity": spec.sensitivity,
                    "capabilities": tuple(sorted(spec.capabilities)),
                    "payload_schema_version": spec.payload_schema_version,
                    "implementation_version": spec.implementation_version,
                    "has_untyped_coercer": spec.coerce_untyped_input is not None,
                    **_provenance_record(self._type_provenance[type_id]),
                }
            )
        for key in sorted(self._conversions):
            conversion = self._conversions[key]
            records.append(
                {
                    "kind": "conversion",
                    "source_type_id": conversion.source_type_id,
                    "target_type_id": conversion.target_type_id,
                    "implementation_version": conversion.implementation_version,
                    **_provenance_record(self._conversion_provenance[key]),
                }
            )
        return tuple(records)


def _validate_provenance(
    owner_id: str, owner_version: str, source_label: str
) -> _Provenance:
    _validate_catalog_identifier(
        owner_id,
        "owner ID",
        max_length=_CATALOG_OWNER_ID_LENGTH,
    )
    _validate_catalog_identifier(
        owner_version,
        "owner version",
        max_length=_CATALOG_VERSION_LENGTH,
        allow_empty=True,
    )
    if not isinstance(source_label, str):
        raise DataTypeCatalogError("source label must be a string")
    return _Provenance(owner_id, owner_version, source_label)


def _validate_family(family: object) -> None:
    if not isinstance(family, DataTypeFamilySpec):
        raise DataTypeCatalogError("families must contain DataTypeFamilySpec records")
    _require_text(family.family_id, "family ID")
    _require_text(family.display_name, f"family {family.family_id!r} display name")
    if not isinstance(family.color_token, str) or not isinstance(family.icon_key, str):
        raise DataTypeCatalogError(
            f"family {family.family_id!r} color token and icon key must be strings"
        )


def _validate_type_spec(spec: object) -> None:
    if not isinstance(spec, DataTypeSpec):
        raise DataTypeCatalogError("types must contain DataTypeSpec records")
    _validate_type_id(spec.type_id, "data-type ID")
    _require_text(spec.display_name, f"type {spec.type_id!r} display name")
    _require_text(spec.family_id, f"type {spec.type_id!r} family ID")
    if not callable(spec.validate_item):
        raise DataTypeCatalogError(
            f"type {spec.type_id!r} validator must be callable"
        )
    if spec.coerce_untyped_input is not None and not callable(
        spec.coerce_untyped_input
    ):
        raise DataTypeCatalogError(
            f"type {spec.type_id!r} untyped coercer must be callable"
        )
    if not isinstance(spec.description, str):
        raise DataTypeCatalogError(
            f"type {spec.type_id!r} description must be a string"
        )
    if type(spec.abstract) is not bool:
        raise DataTypeCatalogError(
            f"type {spec.type_id!r} abstract flag must be a bool"
        )
    if not isinstance(spec.parents, tuple):
        raise DataTypeCatalogError(f"type {spec.type_id!r} parents must be a tuple")
    for parent_id in spec.parents:
        _validate_type_id(parent_id, f"parent ID of type {spec.type_id!r}")
    if len(set(spec.parents)) != len(spec.parents):
        raise DataTypeCatalogError(
            f"type {spec.type_id!r} declares duplicate parents"
        )
    if not isinstance(spec.carriers, frozenset) or not spec.carriers:
        raise DataTypeCatalogError(
            f"type {spec.type_id!r} carriers must be a non-empty frozenset"
        )
    if any(
        not isinstance(carrier, str)
        or not carrier
        or carrier.strip() != carrier
        for carrier in spec.carriers
    ):
        raise DataTypeCatalogError(
            f"type {spec.type_id!r} carrier names must be non-empty, trimmed strings"
        )
    unknown_carriers = spec.carriers - _CARRIER_KINDS
    if unknown_carriers:
        raise DataTypeCatalogError(
            f"type {spec.type_id!r} has unsupported carriers "
            f"{sorted(unknown_carriers)!r}"
        )
    if not isinstance(spec.persistence, str):
        raise DataTypeCatalogError(
            f"type {spec.type_id!r} persistence must be a string"
        )
    if spec.persistence not in _PERSISTENCE_KINDS:
        raise DataTypeCatalogError(
            f"type {spec.type_id!r} has invalid persistence "
            f"{spec.persistence!r}"
        )
    if not isinstance(spec.sensitivity, str):
        raise DataTypeCatalogError(
            f"type {spec.type_id!r} sensitivity must be a string"
        )
    if spec.sensitivity not in _SENSITIVITY_KINDS:
        raise DataTypeCatalogError(
            f"type {spec.type_id!r} has invalid sensitivity "
            f"{spec.sensitivity!r}"
        )
    if spec.persistence == "inline" and not spec.carriers.intersection(
        {"native", "inline"}
    ):
        raise DataTypeCatalogError(
            f"type {spec.type_id!r} inline persistence requires a native or "
            "inline carrier"
        )
    if spec.persistence == "saved_artifact" and "artifact" not in spec.carriers:
        raise DataTypeCatalogError(
            f"type {spec.type_id!r} saved_artifact persistence requires an "
            "artifact carrier"
        )
    if spec.sensitivity == "secret" and spec.persistence != "never":
        raise DataTypeCatalogError(
            f"secret type {spec.type_id!r} must use persistence 'never'"
        )
    if spec.sensitivity == "secret" and "artifact" in spec.carriers:
        raise DataTypeCatalogError(
            f"secret type {spec.type_id!r} must not allow artifact carriers"
        )
    if not isinstance(spec.capabilities, frozenset):
        raise DataTypeCatalogError(
            f"type {spec.type_id!r} capabilities must be a frozenset"
        )
    if any(
        not isinstance(capability, str)
        or not capability
        or capability.strip() != capability
        for capability in spec.capabilities
    ):
        raise DataTypeCatalogError(
            f"type {spec.type_id!r} capability names must be non-empty, "
            "trimmed strings"
        )
    if (
        isinstance(spec.payload_schema_version, bool)
        or not isinstance(spec.payload_schema_version, int)
        or spec.payload_schema_version < 1
        or spec.payload_schema_version > MAX_PAYLOAD_SCHEMA_VERSION
    ):
        raise DataTypeCatalogError(
            f"type {spec.type_id!r} payload schema version must be a positive "
            f"integer no greater than {MAX_PAYLOAD_SCHEMA_VERSION}"
        )
    _validate_catalog_identifier(
        spec.implementation_version,
        f"type {spec.type_id!r} implementation version",
        max_length=_CATALOG_VERSION_LENGTH,
    )


def _validate_conversion(conversion: object) -> None:
    if not isinstance(conversion, DataConversionSpec):
        raise DataTypeCatalogError(
            "conversions must contain DataConversionSpec records"
        )
    _validate_type_id(conversion.source_type_id, "conversion source type ID")
    _validate_type_id(conversion.target_type_id, "conversion target type ID")
    if not callable(conversion.convert_item):
        raise DataTypeCatalogError(
            f"conversion {conversion.source_type_id!r} -> "
            f"{conversion.target_type_id!r} must be callable"
        )
    _validate_catalog_identifier(
        conversion.implementation_version,
        f"conversion {conversion.source_type_id!r} -> "
        f"{conversion.target_type_id!r} implementation version",
        max_length=_CATALOG_VERSION_LENGTH,
    )


def _validate_type_id(value: str, label: str) -> None:
    try:
        validate_canonical_clr_type_id(value)
    except ClrTypeNameError as exc:
        raise DataTypeCatalogError(f"invalid {label} {value!r}: {exc}") from exc


def _validate_catalog_integrity(
    *,
    families: Mapping[str, DataTypeFamilySpec],
    types: Mapping[str, DataTypeSpec],
    conversions: Mapping[tuple[str, str], DataConversionSpec],
) -> dict[str, frozenset[str]]:
    for family in families.values():
        _validate_family(family)
    for spec in types.values():
        _validate_type_spec(spec)
        if spec.family_id not in families:
            raise DataTypeCatalogError(
                f"type {spec.type_id!r} references unknown family "
                f"{spec.family_id!r}"
            )
        for parent_id in spec.parents:
            if parent_id == spec.type_id:
                raise DataTypeCatalogError(
                    f"type {spec.type_id!r} cannot parent itself"
                )
            if parent_id not in types:
                raise DataTypeCatalogError(
                    f"type {spec.type_id!r} references unknown parent "
                    f"{parent_id!r}"
                )

    ancestors = _build_ancestor_closure(types)

    for conversion in conversions.values():
        _validate_conversion(conversion)
        for endpoint in (
            conversion.source_type_id,
            conversion.target_type_id,
        ):
            if endpoint not in types:
                raise DataTypeCatalogError(
                    "conversion "
                    f"{conversion.source_type_id!r} -> "
                    f"{conversion.target_type_id!r} references unknown "
                    f"endpoint {endpoint!r}"
                )
    return ancestors


def _require_text(value: object, label: str) -> None:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise DataTypeCatalogError(f"{label} must be a non-empty, trimmed string")


def _validate_catalog_identifier(
    value: object,
    label: str,
    *,
    max_length: int,
    allow_empty: bool = False,
) -> str:
    if not isinstance(value, str):
        raise DataTypeCatalogError(f"{label} must be a string")
    if value != value.strip():
        raise DataTypeCatalogError(f"{label} must be a trimmed string")
    if not allow_empty and not value:
        raise DataTypeCatalogError(f"{label} must be non-empty")
    if len(value) > max_length:
        raise DataTypeCatalogError(f"{label} is too long")
    if len(value) >= 2 and value[0].isalpha() and value[1] == ":":
        raise DataTypeCatalogError(
            f"{label} must be a path-free semantic identifier"
        )
    if any(
        not (character.isalnum() or character in "._:@+-")
        for character in value
    ):
        raise DataTypeCatalogError(
            f"{label} must be a path-free semantic identifier"
        )
    return value


def _build_ancestor_closure(
    specs: Mapping[str, DataTypeSpec],
) -> dict[str, frozenset[str]]:
    state: dict[str, int] = {}
    result: dict[str, frozenset[str]] = {}
    path: list[str] = []

    def visit(type_id: str) -> frozenset[str]:
        if state.get(type_id) == 2:
            return result[type_id]
        if state.get(type_id) == 1:
            start = path.index(type_id)
            cycle = path[start:] + [type_id]
            raise DataTypeCatalogError(
                f"data-type parent cycle: {' -> '.join(cycle)}"
            )
        state[type_id] = 1
        path.append(type_id)
        ancestors: set[str] = set()
        for parent_id in sorted(specs[type_id].parents):
            if parent_id not in specs:
                raise DataTypeCatalogError(
                    f"type {type_id!r} references unknown parent {parent_id!r}"
                )
            ancestors.add(parent_id)
            ancestors.update(visit(parent_id))
        path.pop()
        state[type_id] = 2
        result[type_id] = frozenset(ancestors)
        return result[type_id]

    for type_id in sorted(specs):
        visit(type_id)
    return result


def _validator_accepts(spec: DataTypeSpec, value: object) -> bool:
    try:
        return bool(spec.validate_item(value))
    except Exception as exc:
        raise DataTypeCatalogError(
            f"validator failed for data type {spec.type_id!r}: {exc}"
        ) from exc


def _provenance_record(provenance: _Provenance) -> dict[str, str]:
    return {
        "owner_id": provenance.owner_id,
        "owner_version": provenance.owner_version,
        "source_label": provenance.source_label,
    }


__all__ = [
    "ARRAY_DATA_REF_TYPE_ID",
    "ARRAY_SLICE_2D_REF_TYPE_ID",
    "BOOLEAN_DATA_TYPE_ID",
    "CONNECTION_FALLBACK_CAPABILITY",
    "COREX_VIEWER_SESSION_HANDLE_KIND",
    "DataConversionSpec",
    "DataTypeCatalog",
    "DataTypeCatalogError",
    "DataTypeCompatibility",
    "DataTypeFamilySpec",
    "DataTypeSpec",
    "DOUBLE_DATA_TYPE_ID",
    "ENGINEERING_SCENE_DATA_TYPE_ID",
    "ENGINEERING_SELECTION_SET_DATA_TYPE_ID",
    "GRAPH_ARRAY_DATA_TYPE_ID",
    "GRAPH_DATA_TYPE_ID",
    "GRAPH_DICTIONARY_DATA_TYPE_ID",
    "INTEGER_DATA_TYPE_ID",
    "INTERVAL_1D_GRAPH_DATA_TYPE_ID",
    "JSON_DATA_TYPE_ID",
    "JSON_VALUE_DATA_TYPE_ID",
    "MAX_PAYLOAD_SCHEMA_VERSION",
    "PATH_DATA_TYPE_ID",
    "PLOT_EXPORT_BUNDLE_DATA_TYPE_ID",
    "STRING_DATA_TYPE_ID",
    "STRING_LIST_DATA_TYPE_ID",
    "TABULAR_DATA_REF_TYPE_ID",
    "TABULAR_WINDOW_REF_TYPE_ID",
    "TypeCarrierKind",
    "TypePersistence",
    "TypeSensitivity",
    "VIEWER_SESSION_DATA_TYPE_ID",
]
