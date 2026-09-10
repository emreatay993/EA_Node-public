from __future__ import annotations

import ast
import dataclasses
import importlib
import inspect
from collections.abc import Callable

import pytest

from ea_node_editor.runtime_contracts import (
    DataConversionSpec,
    DataTypeCatalog,
    DataTypeCatalogError,
    DataTypeCompatibility,
    DataTypeFamilySpec,
    DataTypeSpec,
)
from ea_node_editor.runtime_contracts.data_types import MAX_PAYLOAD_SCHEMA_VERSION

FAMILY = DataTypeFamilySpec("test", "Test", "type.test", "test")


def type_spec(
    type_id: str,
    *,
    parents: tuple[str, ...] = (),
    abstract: bool = False,
    validator: Callable[[object], bool] = lambda _value: True,
    coercer: Callable[[object], object] | None = None,
    description: str = "",
    carriers: frozenset[str] = frozenset({"native"}),
    persistence: str = "never",
    sensitivity: str = "normal",
    capabilities: frozenset[str] = frozenset(),
    payload_schema_version: int = 1,
    implementation_version: str = "1",
) -> DataTypeSpec:
    return DataTypeSpec(
        type_id=type_id,
        display_name=type_id.rsplit(".", 1)[-1],
        family_id=FAMILY.family_id,
        validate_item=validator,
        coerce_untyped_input=coercer,
        description=description,
        parents=parents,
        abstract=abstract,
        carriers=carriers,  # type: ignore[arg-type]
        persistence=persistence,  # type: ignore[arg-type]
        sensitivity=sensitivity,  # type: ignore[arg-type]
        capabilities=capabilities,
        payload_schema_version=payload_schema_version,
        implementation_version=implementation_version,
    )


def catalog_with(
    *specs: DataTypeSpec,
    conversions: tuple[DataConversionSpec, ...] = (),
    source_label: str = "fixture",
    owner_version: str = "1",
) -> DataTypeCatalog:
    catalog = DataTypeCatalog()
    catalog.register_many(
        families=(FAMILY,),
        types=specs,
        conversions=conversions,
        owner_id="tests",
        owner_version=owner_version,
        source_label=source_label,
    )
    return catalog


def test_multiple_parent_dag_accepts_same_batch_parents_and_builds_closure() -> None:
    catalog = catalog_with(
        type_spec("Test.Leaf", parents=("Test.Left", "Test.Right")),
        type_spec("Test.Right", parents=("Test.Root",)),
        type_spec("Test.Root", abstract=True),
        type_spec("Test.Left", parents=("Test.Root",)),
    )

    assert catalog.is_assignable("Test.Leaf", "Test.Leaf")
    assert catalog.is_assignable("Test.Leaf", "Test.Left")
    assert catalog.is_assignable("Test.Leaf", "Test.Right")
    assert catalog.is_assignable("Test.Leaf", "Test.Root")
    assert not catalog.is_assignable("Test.Left", "Test.Right")
    assert [spec.type_id for spec in catalog.all_specs()] == [
        "Test.Leaf",
        "Test.Left",
        "Test.Right",
        "Test.Root",
    ]


def test_failed_batch_rolls_back_families_types_conversions_and_provenance() -> None:
    catalog = catalog_with(type_spec("Test.Root"))
    before = catalog.snapshot()

    with pytest.raises(DataTypeCatalogError, match="Test.Missing"):
        catalog.register_many(
            families=(DataTypeFamilySpec("new", "New", "", ""),),
            types=(
                DataTypeSpec(
                    "Test.Child",
                    "Child",
                    "new",
                    lambda _value: True,
                    parents=("Test.Missing",),
                ),
            ),
            conversions=(
                DataConversionSpec("Test.Root", "Test.Child", lambda value: value),
            ),
            owner_id="bad-owner",
        )

    assert catalog.snapshot() == before
    assert catalog.get("Test.Child") is None
    assert catalog.owner_of("Test.Root") == "tests"


def test_owner_exclusion_can_be_repaired_by_the_replacement_batch() -> None:
    family = DataTypeFamilySpec("shared", "Shared", "type.shared", "shared")
    owner_type = DataTypeSpec(
        "Shared.Owner",
        "Owner",
        family.family_id,
        lambda _value: True,
    )
    dependent_type = DataTypeSpec(
        "Shared.Dependent",
        "Dependent",
        family.family_id,
        lambda _value: True,
        parents=("Shared.Owner",),
    )
    catalog = DataTypeCatalog()
    catalog.register_many(
        families=(family,),
        types=(owner_type,),
        owner_id="owner-a",
    )
    catalog.register_many(
        types=(dependent_type,),
        conversions=(
            DataConversionSpec(
                "Shared.Dependent",
                "Shared.Owner",
                lambda value: value,
            ),
        ),
        owner_id="owner-b",
    )

    staged = catalog.fork(excluding_owner_id="owner-a")
    staged.register_many(
        families=(family,),
        types=(owner_type,),
        owner_id="owner-a",
    )

    assert staged.is_assignable("Shared.Dependent", "Shared.Owner")
    assert (
        staged.compatibility("Shared.Dependent", "Shared.Owner").status
        == "assignable"
    )


def test_freeze_rejects_family_removed_by_owner_exclusion() -> None:
    catalog = DataTypeCatalog()
    catalog.register_many(families=(FAMILY,), owner_id="family-owner")
    catalog.register_many(
        types=(type_spec("Test.Dependent"),),
        owner_id="type-owner",
    )

    staged = catalog.fork(excluding_owner_id="family-owner")

    with pytest.raises(DataTypeCatalogError, match="references unknown family 'test'"):
        staged.freeze()
    assert not staged.is_frozen


def test_freeze_rejects_conversion_endpoint_removed_by_owner_exclusion() -> None:
    catalog = DataTypeCatalog()
    catalog.register_many(families=(FAMILY,), owner_id="family-owner")
    catalog.register_many(
        types=(type_spec("Test.Removed"),),
        owner_id="removed-owner",
    )
    catalog.register_many(
        types=(type_spec("Test.Remaining"),),
        conversions=(
            DataConversionSpec(
                "Test.Remaining",
                "Test.Removed",
                lambda value: value,
            ),
        ),
        owner_id="remaining-owner",
    )

    staged = catalog.fork(excluding_owner_id="removed-owner")

    with pytest.raises(
        DataTypeCatalogError,
        match="references unknown endpoint 'Test.Removed'",
    ):
        staged.freeze()
    assert not staged.is_frozen


@pytest.mark.parametrize(
    ("field_name", "malicious_value"),
    [
        ("owner_id", r"C:\private\catalog.py"),
        ("owner_id", "C:private"),
        ("owner_id", "tests\nsecret"),
        ("owner_id", "x" * 257),
        ("owner_version", "/opt/private/catalog.py"),
        ("owner_version", "C:private"),
        ("owner_version", "1\nsecret"),
        ("owner_version", "x" * 129),
        ("type_implementation_version", r"C:\private\validator.py"),
        ("type_implementation_version", "C:private"),
        ("type_implementation_version", "1\nsecret"),
        ("type_implementation_version", "x" * 129),
        ("conversion_implementation_version", "/opt/private/converter.py"),
        ("conversion_implementation_version", "C:private"),
        ("conversion_implementation_version", "1\nsecret"),
        ("conversion_implementation_version", "x" * 129),
    ],
)
def test_catalog_semantic_identifiers_reject_paths_controls_and_unbounded_values(
    field_name: str,
    malicious_value: str,
) -> None:
    catalog = DataTypeCatalog()
    owner_id = malicious_value if field_name == "owner_id" else "tests"
    owner_version = (
        malicious_value if field_name == "owner_version" else "1"
    )
    type_version = (
        malicious_value
        if field_name == "type_implementation_version"
        else "1"
    )
    conversion_version = (
        malicious_value
        if field_name == "conversion_implementation_version"
        else "1"
    )

    with pytest.raises(DataTypeCatalogError) as error:
        catalog.register_many(
            families=(FAMILY,),
            types=(
                type_spec(
                    "Test.Source",
                    implementation_version=type_version,
                ),
                type_spec("Test.Target"),
            ),
            conversions=(
                DataConversionSpec(
                    "Test.Source",
                    "Test.Target",
                    lambda value: value,
                    implementation_version=conversion_version,
                ),
            ),
            owner_id=owner_id,
            owner_version=owner_version,
        )

    assert malicious_value not in str(error.value)
    assert catalog.snapshot() == ()


def test_catalog_rejects_payload_schema_version_above_shared_limit_atomically() -> None:
    catalog = DataTypeCatalog()

    with pytest.raises(DataTypeCatalogError, match="payload schema version"):
        catalog.register_many(
            families=(FAMILY,),
            types=(
                type_spec(
                    "Test.OversizedSchema",
                    payload_schema_version=MAX_PAYLOAD_SCHEMA_VERSION + 1,
                ),
            ),
            owner_id="tests",
        )

    assert catalog.snapshot() == ()


@pytest.mark.parametrize("invalid_version", [True, 0])
def test_catalog_rejects_boolean_and_zero_payload_schema_versions_atomically(
    invalid_version: object,
) -> None:
    catalog = DataTypeCatalog()

    with pytest.raises(DataTypeCatalogError, match="payload schema version"):
        catalog.register_many(
            families=(FAMILY,),
            types=(
                type_spec(
                    "Test.InvalidSchemaBoundary",
                    payload_schema_version=invalid_version,  # type: ignore[arg-type]
                ),
            ),
            owner_id="tests",
        )

    assert catalog.snapshot() == ()


def test_catalog_accepts_maximum_payload_schema_version() -> None:
    catalog = DataTypeCatalog()
    catalog.register_many(
        families=(FAMILY,),
        types=(
            type_spec(
                "Test.MaximumSchema",
                payload_schema_version=MAX_PAYLOAD_SCHEMA_VERSION,
            ),
        ),
        owner_id="tests",
    )

    type_record = next(
        record for record in catalog.snapshot() if record["kind"] == "type"
    )
    assert type_record["payload_schema_version"] == MAX_PAYLOAD_SCHEMA_VERSION


@pytest.mark.parametrize(
    ("specs", "message"),
    [
        (
            (type_spec("Test.Child", parents=("Test.Missing",)),),
            "unknown parent 'Test.Missing'",
        ),
        (
            (type_spec("Test.Self", parents=("Test.Self",)),),
            "cannot parent itself",
        ),
        (
            (
                type_spec("Test.One", parents=("Test.Two",)),
                type_spec("Test.Two", parents=("Test.One",)),
            ),
            "parent cycle",
        ),
        (
            (type_spec("Test.Type, Test.Assembly"),),
            "invalid data-type ID",
        ),
        (
            (type_spec("Test.Type]"),),
            "invalid data-type ID",
        ),
    ],
)
def test_rejects_missing_self_cycle_and_malformed_ids(
    specs: tuple[DataTypeSpec, ...], message: str
) -> None:
    with pytest.raises(DataTypeCatalogError, match=message):
        catalog_with(*specs)


def test_rejects_duplicate_family_type_and_conversion_declarations() -> None:
    with pytest.raises(DataTypeCatalogError, match="duplicate data-type family"):
        DataTypeCatalog().register_many(
            families=(FAMILY, FAMILY),
            owner_id="tests",
        )

    with pytest.raises(DataTypeCatalogError, match="duplicate data-type ID"):
        catalog_with(type_spec("Test.One"), type_spec("Test.One"))

    conversion = DataConversionSpec("Test.One", "Test.Two", lambda value: value)
    with pytest.raises(DataTypeCatalogError, match="duplicate data conversion"):
        catalog_with(
            type_spec("Test.One"),
            type_spec("Test.Two"),
            conversions=(conversion, conversion),
        )


def test_rejects_unknown_conversion_endpoint_and_freeze_blocks_mutation() -> None:
    catalog = catalog_with(type_spec("Test.One"))
    before = catalog.snapshot()

    with pytest.raises(DataTypeCatalogError, match="unknown endpoint 'Test.Missing'"):
        catalog.register_many(
            conversions=(
                DataConversionSpec("Test.One", "Test.Missing", lambda value: value),
            ),
            owner_id="tests",
        )
    assert catalog.snapshot() == before

    catalog.freeze()
    catalog.freeze()
    with pytest.raises(DataTypeCatalogError, match="frozen"):
        catalog.register_many(owner_id="tests")


def test_direct_conversion_works_but_conversion_chaining_is_never_searched() -> None:
    catalog = catalog_with(
        type_spec("Test.A", validator=lambda value: isinstance(value, str)),
        type_spec("Test.B", validator=lambda value: isinstance(value, int)),
        type_spec("Test.C", validator=lambda value: isinstance(value, float)),
        conversions=(
            DataConversionSpec("Test.A", "Test.B", int),
            DataConversionSpec("Test.B", "Test.C", float),
        ),
    )

    assert catalog.compatibility("Test.A", "Test.B").status == "convertible"
    assert catalog.convert_typed_input("Test.A", "Test.B", "4") == 4
    assert catalog.compatibility("Test.A", "Test.C").status == "incompatible"
    with pytest.raises(DataTypeCatalogError, match="not convertible"):
        catalog.convert_typed_input("Test.A", "Test.C", "4")


def test_accepted_union_uses_strongest_relation_then_declaration_order() -> None:
    catalog = catalog_with(
        type_spec("Test.Parent", abstract=True),
        type_spec("Test.Source", parents=("Test.Parent",)),
        type_spec("Test.Primary"),
        type_spec("Test.First"),
        type_spec("Test.Second"),
        type_spec("Test.Interface", abstract=True),
        type_spec("Test.Concrete", parents=("Test.Interface",)),
        type_spec("Test.Converted"),
        conversions=(
            DataConversionSpec("Test.Source", "Test.Primary", lambda value: value),
            DataConversionSpec("Test.Source", "Test.First", lambda value: value),
            DataConversionSpec("Test.Source", "Test.Second", lambda value: value),
            DataConversionSpec("Test.Interface", "Test.Converted", lambda value: value),
        ),
    )

    exact = catalog.compatibility(
        "Test.Source",
        "Test.Primary",
        ("Test.First", "Test.Source"),
    )
    assert exact.status == "assignable"
    assert exact.reason_code == "exact"
    assert exact.matched_type_id == "Test.Source"

    parent = catalog.compatibility(
        "Test.Source",
        "Test.Primary",
        ("Test.Parent",),
    )
    assert parent.status == "assignable"
    assert parent.reason_code == "declared_parent"
    assert parent.matched_type_id == "Test.Parent"

    first_conversion = catalog.compatibility(
        "Test.Source",
        "Test.Primary",
        ("Test.First", "Test.Second"),
    )
    assert first_conversion.status == "convertible"
    assert first_conversion.is_compatible
    assert first_conversion.matched_type_id == "Test.Primary"

    conversion_over_runtime_check = catalog.compatibility(
        "Test.Interface",
        "Test.Concrete",
        ("Test.Converted",),
    )
    assert conversion_over_runtime_check.status == "convertible"
    assert conversion_over_runtime_check.matched_type_id == "Test.Converted"

    exact_after_unresolved = catalog.compatibility(
        "Test.Source",
        "Test.Missing",
        ("Test.Source",),
    )
    assert exact_after_unresolved.status == "assignable"
    assert exact_after_unresolved.matched_type_id == "Test.Source"

    first_unresolved = catalog.compatibility(
        "Test.Source",
        "Test.Missing",
        ("Test.AlsoMissing",),
    )
    assert first_unresolved.status == "unresolved"
    assert first_unresolved.matched_type_id == "Test.Missing"
    assert not catalog.compatibility(
        "Test.Source",
        "Test.Unrelated",
    ).is_compatible


def test_abstract_source_runtime_check_only_applies_to_actual_descendants() -> None:
    catalog = catalog_with(
        type_spec("Test.Interface", abstract=True),
        type_spec("Test.Concrete", parents=("Test.Interface",)),
        type_spec("Test.Unrelated"),
    )

    assert (
        catalog.compatibility("Test.Concrete", "Test.Interface").status
        == "assignable"
    )
    runtime_check = catalog.compatibility("Test.Interface", "Test.Concrete")
    assert runtime_check.status == "runtime_check"
    assert runtime_check.matched_type_id == "Test.Concrete"
    assert (
        catalog.compatibility("Test.Interface", "Test.Unrelated").status
        == "incompatible"
    )
    assert (
        catalog.compatibility("Test.Missing", "Test.Concrete").status
        == "unresolved"
    )
    assert (
        catalog.compatibility("Test.Concrete", "Test.Missing").status
        == "unresolved"
    )


def test_none_is_universally_accepted_without_validation_or_conversion() -> None:
    calls: list[str] = []
    catalog = catalog_with(
        type_spec(
            "Test.Source",
            validator=lambda _value: calls.append("source") or False,
        ),
        type_spec(
            "Test.Target",
            validator=lambda _value: calls.append("target") or False,
            coercer=lambda _value: calls.append("coerce"),
        ),
        conversions=(
            DataConversionSpec(
                "Test.Source",
                "Test.Target",
                lambda _value: calls.append("convert"),
            ),
        ),
    )

    assert catalog.prepare_untyped_input("Test.Target", None) is None
    assert catalog.convert_typed_input("Test.Source", "Test.Target", None) is None
    assert catalog.validate_output("Test.Target", None) is None
    assert calls == []


def test_untyped_input_coerces_only_when_invalid_and_output_never_coerces() -> None:
    calls: list[object] = []
    marker = object()
    catalog = catalog_with(
        type_spec(
            "Test.Int",
            validator=lambda value: isinstance(value, int),
            coercer=lambda value: calls.append(value) or int(value),
        ),
        type_spec("Test.Marker", validator=lambda value: value is marker),
    )

    assert catalog.prepare_untyped_input("Test.Int", 3) == 3
    assert catalog.prepare_untyped_input("Test.Int", "4") == 4
    assert calls == ["4"]
    assert catalog.convert_typed_input("Test.Marker", "Test.Marker", marker) is marker
    with pytest.raises(DataTypeCatalogError, match="output value is invalid"):
        catalog.validate_output("Test.Int", "5")
    assert calls == ["4"]


def test_abstract_output_uses_concrete_descendant_validators() -> None:
    catalog = catalog_with(
        type_spec(
            "Test.Abstract",
            abstract=True,
            validator=lambda _value: False,
        ),
        type_spec(
            "Test.Integer",
            parents=("Test.Abstract",),
            validator=lambda value: isinstance(value, int),
        ),
    )

    catalog.validate_output("Test.Abstract", 3)
    with pytest.raises(DataTypeCatalogError, match="output value is invalid"):
        catalog.validate_output("Test.Abstract", object())


def test_runtime_check_validates_actual_target_and_reports_validator_failures() -> None:
    catalog = catalog_with(
        type_spec("Test.Interface", abstract=True),
        type_spec(
            "Test.Concrete",
            parents=("Test.Interface",),
            validator=lambda value: value == "valid",
        ),
        type_spec(
            "Test.Broken",
            validator=lambda _value: (_ for _ in ()).throw(RuntimeError("broken")),
        ),
    )

    assert (
        catalog.convert_typed_input("Test.Interface", "Test.Concrete", "valid")
        == "valid"
    )
    with pytest.raises(DataTypeCatalogError, match="does not satisfy target"):
        catalog.convert_typed_input("Test.Interface", "Test.Concrete", "invalid")
    with pytest.raises(DataTypeCatalogError, match="validator failed.*broken"):
        catalog.prepare_untyped_input("Test.Broken", "value")


def test_converter_failure_and_invalid_converted_value_are_rejected() -> None:
    broken = catalog_with(
        type_spec("Test.Source"),
        type_spec("Test.Target"),
        conversions=(
            DataConversionSpec(
                "Test.Source",
                "Test.Target",
                lambda _value: (_ for _ in ()).throw(RuntimeError("broken")),
            ),
        ),
    )
    with pytest.raises(DataTypeCatalogError, match="conversion.*broken"):
        broken.convert_typed_input("Test.Source", "Test.Target", "value")

    invalid = catalog_with(
        type_spec("Test.Source"),
        type_spec("Test.Target", validator=lambda value: isinstance(value, int)),
        conversions=(
            DataConversionSpec("Test.Source", "Test.Target", lambda _value: "bad"),
        ),
    )
    with pytest.raises(DataTypeCatalogError, match="output value is invalid"):
        invalid.convert_typed_input("Test.Source", "Test.Target", "value")


def _fingerprint_catalog(
    *,
    reverse: bool,
    implementation_version: str = "1",
    conversion_version: str = "conversion-v1",
    owner_version: str = "1",
) -> DataTypeCatalog:
    specs = [
        type_spec("Test.Root", abstract=True),
        type_spec(
            "Test.Leaf",
            parents=("Test.Root",),
            validator=lambda _value: True,
            coercer=lambda value: value,
            implementation_version=implementation_version,
        ),
    ]
    if reverse:
        specs.reverse()
    catalog = catalog_with(
        *specs,
        conversions=(
            DataConversionSpec(
                "Test.Root",
                "Test.Leaf",
                lambda value: value,
                implementation_version=conversion_version,
            ),
        ),
        owner_version=owner_version,
    )
    return catalog


def test_fingerprint_is_order_and_callable_identity_independent_but_versioned() -> None:
    first = _fingerprint_catalog(reverse=False)
    second = _fingerprint_catalog(reverse=True)
    changed = _fingerprint_catalog(reverse=False, implementation_version="2")
    conversion_changed = _fingerprint_catalog(
        reverse=False,
        conversion_version="conversion-v2",
    )
    owner_changed = _fingerprint_catalog(reverse=False, owner_version="2")

    assert first.fingerprint() == second.fingerprint()
    assert first.snapshot() == second.snapshot()
    assert first.fingerprint() != changed.fingerprint()
    assert first.fingerprint() != conversion_changed.fingerprint()
    assert first.fingerprint() != owner_changed.fingerprint()
    assert len(first.fingerprint()) == 64


def test_fingerprint_ignores_local_source_label_but_snapshot_retains_it() -> None:
    first = catalog_with(
        type_spec("Test.Type"),
        source_label=r"C:\private\plugins\catalog.py",
    )
    second = catalog_with(
        type_spec("Test.Type"),
        source_label="/opt/private/plugins/catalog.py",
    )

    assert first.fingerprint() == second.fingerprint()
    assert first.snapshot() != second.snapshot()
    assert {
        record["source_label"] for record in first.snapshot()
    } == {r"C:\private\plugins\catalog.py"}
    assert {
        record["source_label"] for record in second.snapshot()
    } == {"/opt/private/plugins/catalog.py"}


def test_snapshot_and_provenance_are_immutable_and_do_not_expose_catalog_state() -> None:
    catalog = catalog_with(
        type_spec(
            "Test.Type",
            carriers=frozenset({"native", "inline"}),
            capabilities=frozenset({"preview", "measure"}),
        )
    )
    snapshot = catalog.snapshot()
    type_record = next(record for record in snapshot if record["kind"] == "type")

    assert catalog.owner_of("Test.Type") == "tests"
    assert type_record["owner_version"] == "1"
    assert type_record["source_label"] == "fixture"
    assert type_record["carriers"] == ("inline", "native")
    assert type_record["capabilities"] == ("measure", "preview")
    with pytest.raises(TypeError):
        type_record["owner_id"] = "mutated"  # type: ignore[index]
    assert catalog.owner_of("Test.Type") == "tests"


def test_mutable_description_is_rejected_without_snapshot_or_fingerprint_leak() -> None:
    catalog = catalog_with(type_spec("Test.Existing"))
    before_snapshot = catalog.snapshot()
    before_fingerprint = catalog.fingerprint()
    mutable_description: list[str] = ["initial"]

    with pytest.raises(DataTypeCatalogError, match="description must be a string"):
        catalog.register_many(
            types=(
                type_spec(
                    "Test.Invalid",
                    description=mutable_description,  # type: ignore[arg-type]
                ),
            ),
            owner_id="tests",
        )

    mutable_description.append("changed")
    assert catalog.snapshot() == before_snapshot
    assert catalog.fingerprint() == before_fingerprint
    assert catalog.get("Test.Invalid") is None


def test_truthy_string_abstract_flag_cannot_create_runtime_check_compatibility() -> None:
    catalog = catalog_with(
        type_spec("Test.Interface"),
        type_spec("Test.Concrete", parents=("Test.Interface",)),
    )

    with pytest.raises(DataTypeCatalogError, match="abstract flag must be a bool"):
        catalog.register_many(
            types=(
                type_spec(
                    "Test.InvalidInterface",
                    abstract="false",  # type: ignore[arg-type]
                ),
            ),
            owner_id="tests",
        )

    assert (
        catalog.compatibility("Test.Interface", "Test.Concrete").status
        == "incompatible"
    )
    assert catalog.get("Test.InvalidInterface") is None


@pytest.mark.parametrize(
    ("field_name", "value", "message"),
    [
        ("persistence", [], "persistence must be a string"),
        ("sensitivity", {}, "sensitivity must be a string"),
        ("carriers", ("native",), "carriers must be a non-empty frozenset"),
        ("carriers", frozenset({1}), "carrier names"),
        ("capabilities", ["preview"], "capabilities must be a frozenset"),
        ("capabilities", frozenset({1}), "capability names"),
        ("capabilities", frozenset({" preview"}), "capability names"),
    ],
)
def test_malformed_declaration_field_types_raise_catalog_error(
    field_name: str, value: object, message: str
) -> None:
    malformed = dataclasses.replace(
        type_spec("Test.InvalidField"),
        **{field_name: value},
    )

    with pytest.raises(DataTypeCatalogError, match=message):
        catalog_with(malformed)


@pytest.mark.parametrize(
    ("carriers", "persistence", "sensitivity", "message"),
    [
        (frozenset(), "never", "normal", "non-empty frozenset"),
        (frozenset({"unknown"}), "never", "normal", "unsupported carriers"),
        (frozenset({"handle"}), "inline", "normal", "inline persistence"),
        (frozenset({"native"}), "saved_artifact", "normal", "artifact carrier"),
        (frozenset({"native"}), "inline", "secret", "persistence 'never'"),
    ],
)
def test_rejects_invalid_carrier_persistence_and_secret_combinations(
    carriers: frozenset[str],
    persistence: str,
    sensitivity: str,
    message: str,
) -> None:
    with pytest.raises(DataTypeCatalogError, match=message):
        catalog_with(
            type_spec(
                "Test.Invalid",
                carriers=carriers,
                persistence=persistence,
                sensitivity=sensitivity,
            )
        )


def test_public_records_are_frozen_slotted_and_module_has_no_catalog_singleton() -> None:
    for record_type in (
        DataTypeFamilySpec,
        DataTypeSpec,
        DataConversionSpec,
        DataTypeCompatibility,
    ):
        assert dataclasses.is_dataclass(record_type)
        assert "__slots__" in record_type.__dict__

    with pytest.raises(dataclasses.FrozenInstanceError):
        FAMILY.display_name = "Changed"  # type: ignore[misc]

    module = importlib.import_module("ea_node_editor.runtime_contracts.data_types")
    assert not any(
        isinstance(value, DataTypeCatalog) for value in vars(module).values()
    )


def test_catalog_module_keeps_the_dependency_boundary() -> None:
    module = importlib.import_module("ea_node_editor.runtime_contracts.data_types")
    tree = ast.parse(inspect.getsource(module))
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imports.update(
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    )

    forbidden = (
        "ea_node_editor.graph",
        "ea_node_editor.execution",
        "ea_node_editor.persistence",
        "ea_node_editor.nodes",
        "ea_node_editor.ui",
        "ea_node_editor.ui_qml",
    )
    assert not any(
        imported == prefix or imported.startswith(f"{prefix}.")
        for imported in imports
        for prefix in forbidden
    )
