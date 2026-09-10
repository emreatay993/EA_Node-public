from __future__ import annotations

import math
from uuid import uuid4

import pandas as pd
import pytest

from ea_node_editor.addons.mechanical import contracts as mechanical_contracts
from ea_node_editor.addons.mechanical.catalog import MECHANICAL_PLUGIN_BACKEND
from ea_node_editor.addons.registry_contributions import register_plugin_backends
from ea_node_editor.addons.mechanical.contracts import (
    CAMERA_VIEW_TYPE_ID,
    CATALOGUE_COLUMNS,
    DEFINITIONS_COLUMNS,
    MECHANICAL_DATA_TYPE_FAMILY,
    MECHANICAL_DATA_TYPES,
    MODEL_TYPE_ID,
    OBJECT_TYPE_ID,
    PROPERTY_TYPE_ID,
    camera_view_value,
    catalogue_table,
    decode_selector,
    definitions_table,
    encode_selector,
    model_handle,
    object_value,
    property_value,
    validate_camera_view,
    validate_model,
    validate_object,
    validate_property,
)
from ea_node_editor.common.payload_tools import REF_METADATA_MAX_BYTES
from ea_node_editor.runtime_contracts import (
    DataTypeCatalog,
    RuntimeHandleRef,
    TypedInlineValue,
)
from ea_node_editor.runtime_contracts.scientific_codec import (
    scientific_from_payload,
    scientific_to_payload,
)
from ea_node_editor.nodes.bootstrap import build_builtin_registry


def _identity() -> dict[str, object]:
    return {
        "run_id": "run-1",
        "session_id": "session-1",
        "document_id": "document-1",
        "source_key": "source-1",
        "system_key": "system-1",
        "model_revision": 2,
    }


def _selector(kind: str, native_id: str | int, path="Model/Load") -> str:
    return encode_selector(
        kind,
        document_id="document-1",
        system_key="system-1",
        object_path=path,
        native_id=native_id,
    )


def _object_payload(**changes):
    payload = {
        **_identity(),
        "object_id": 42,
        "parent_id": None,
        "object_path": "Model/Load",
        "display_name": "Load",
        "api_type": "Ansys.ACT.Automation.Mechanical.Force",
        "category": "load",
        "analysis_id": 7,
        "selector_code": _selector("object", 42),
    }
    payload.update(changes)
    return payload


def _property_payload(**changes):
    payload = {
        **_identity(),
        "object_id": 42,
        "object_path": "Model/Load",
        "property_key": "Magnitude",
        "caption": "Magnitude",
        "definition_kind": "quantity",
        "display_value": "Free",
        "value_status": "free",
        "scalar_value": None,
        "unit": "N",
        "quantity_name": "Force",
        "formula": "",
        "has_tabular_data": False,
        "tables": [],
        "selector_code": _selector("property", "Magnitude"),
    }
    payload.update(changes)
    return payload


def _camera_payload(**changes):
    payload = {
        **_identity(),
        "kind": "saved",
        "name": "Iso",
        "index": 3,
        "focal_point": [0.0, 1.0, 2.0],
        "up_vector": [0.0, 1.0, 0.0],
        "view_vector": [1.0, 0.0, 0.0],
        "scene_width": 10.0,
        "scene_height": 8.0,
        "length_unit": "mm",
        "availability_notes": {},
        "selector_code": _selector("camera_view", 3, ""),
    }
    payload.update(changes)
    return payload


def _model_metadata(**changes):
    payload = {
        **_identity(),
        "workspace_id": "workspace-1",
        "connection_generation": 0,
        "release_code": 261,
        "backend_mode": "background",
        "catalogue_id": str(uuid4()),
        "producer_node_id": "open-1",
        "producer_port": "info",
        "producer_path": [0, 2],
        "producer_iteration": 1,
    }
    payload.update(changes)
    return payload


def _row(kind="session", **changes):
    row = {column: "" for column in CATALOGUE_COLUMNS}
    row.update(
        schema_version=1,
        model_revision=2,
        producer_iteration=1,
        record_kind=kind,
        catalogue_id="00000000-0000-0000-0000-000000000001",
        producer_node_id="open-1",
        producer_port="info",
        producer_path="[0,2]",
        run_id="run-1",
        session_id="session-1",
        document_id="document-1",
        source_key="source-1",
        object_id=None,
        parent_id=None,
        analysis_id=None,
        scalar_value=None,
        has_tabular_data=None,
        row_count=None,
        column_count=None,
        view_index=None,
        omitted_rows=0 if kind == "session" else None,
        catalogue_complete=True if kind == "session" else None,
        related_object_id=None,
        scope_count=None,
        body_hidden=None,
    )
    row.update(changes)
    return row


def test_semantic_types_are_transient_and_use_expected_carriers() -> None:
    assert [spec.type_id for spec in MECHANICAL_DATA_TYPES] == [
        MODEL_TYPE_ID,
        OBJECT_TYPE_ID,
        PROPERTY_TYPE_ID,
        CAMERA_VIEW_TYPE_ID,
    ]
    assert [spec.carriers for spec in MECHANICAL_DATA_TYPES] == [
        frozenset({"handle"}),
        frozenset({"inline"}),
        frozenset({"inline"}),
        frozenset({"inline"}),
    ]
    assert all(spec.persistence == "never" for spec in MECHANICAL_DATA_TYPES)


def test_selector_preserves_string_integer_identity_and_rejects_bool() -> None:
    text = decode_selector(_selector("object", "42"))
    number = decode_selector(_selector("object", 42))
    assert text["native_id"] == "42" and type(text["native_id"]) is str
    assert number["native_id"] == 42 and type(number["native_id"]) is int
    with pytest.raises(TypeError, match="native_id"):
        _selector("object", True)
    with pytest.raises(ValueError, match="unexpected fields"):
        decode_selector(
            '{"schema_version":1,"kind":"x","document_id":"d","system_key":"s","object_path":[],"native_id":1,"extra":0}'
        )


def test_model_metadata_is_exact_workspace_scoped_and_bounded() -> None:
    value = model_handle(
        handle_id="handle-1",
        owner_scope="run-1",
        worker_generation=3,
        metadata=_model_metadata(),
    )
    assert validate_model(value)
    with pytest.raises(ValueError, match="unexpected fields"):
        model_handle(
            handle_id="h",
            owner_scope="r",
            worker_generation=0,
            metadata=_model_metadata(extra=1),
        )
    with pytest.raises(ValueError, match="at least 261"):
        model_handle(
            handle_id="h",
            owner_scope="r",
            worker_generation=0,
            metadata=_model_metadata(release_code=252),
        )
    with pytest.raises(ValueError, match=f"{REF_METADATA_MAX_BYTES} bytes"):
        RuntimeHandleRef(
            MODEL_TYPE_ID,
            1,
            "h",
            "mechanical.model",
            "r",
            0,
            {"text": "x" * REF_METADATA_MAX_BYTES},
        )


@pytest.mark.parametrize(
    ("factory", "validator", "payload", "field"),
    [
        (object_value, validate_object, _object_payload(), "object"),
        (property_value, validate_property, _property_payload(), "property"),
        (camera_view_value, validate_camera_view, _camera_payload(), "camera"),
    ],
)
def test_inline_contracts_accept_exact_snapshots(
    factory, validator, payload, field
) -> None:
    value = factory(payload)
    assert validator(value)
    with pytest.raises(ValueError, match="unexpected fields"):
        factory({**payload, "extra": field})


def test_object_identity_rejects_wrong_model_path_or_selector() -> None:
    with pytest.raises(ValueError, match="selector identity"):
        object_value(_object_payload(system_key="other"))
    with pytest.raises((TypeError, ValueError), match="object_path"):
        object_value(_object_payload(object_path=""))
    with pytest.raises(ValueError, match="selector identity"):
        object_value(_object_payload(document_id="other-document"))
    with pytest.raises(ValueError, match="model_revision"):
        object_value(_object_payload(model_revision=-1))


def test_inline_contract_rejects_wrong_schema_type_and_size() -> None:
    assert not validate_object(TypedInlineValue(OBJECT_TYPE_ID, 2, _object_payload()))
    assert not validate_object(TypedInlineValue(PROPERTY_TYPE_ID, 1, _object_payload()))
    with pytest.raises(ValueError, match="1048576 bytes"):
        object_value(_object_payload(display_name="x" * (1024 * 1024)))


def test_property_preserves_free_null_and_table_unknown_counts() -> None:
    free = property_value(_property_payload())
    assert free.payload["value_status"] == "free"
    assert free.payload["scalar_value"] is None
    value = property_value(
        _property_payload(
            value_status="available",
            has_tabular_data=True,
            display_value="Tabular",
            tables=[
                {
                    "table_key": "definition",
                    "table_family": "field",
                    "definition_kind": "tabular",
                    "row_count": None,
                    "column_count": None,
                }
            ],
        )
    )
    assert value.payload["tables"][0]["row_count"] is None
    with pytest.raises((TypeError, ValueError), match="finite"):
        property_value(_property_payload(scalar_value=math.inf))


@pytest.mark.parametrize("field", ["focal_point", "up_vector", "view_vector"])
def test_camera_rejects_nonfinite_or_wrong_length_vectors(field: str) -> None:
    with pytest.raises(ValueError, match="finite"):
        camera_view_value(_camera_payload(**{field: [0.0, math.nan, 1.0]}))
    with pytest.raises(ValueError, match=field):
        camera_view_value(_camera_payload(**{field: [0.0, 1.0]}))


@pytest.mark.parametrize(
    "field",
    [
        "focal_point",
        "up_vector",
        "view_vector",
        "scene_width",
        "scene_height",
        "length_unit",
    ],
)
def test_camera_unavailable_fields_require_explicit_notes(field: str) -> None:
    value = camera_view_value(
        _camera_payload(
            **{
                field: None,
                "availability_notes": {field: "API field unavailable"},
            }
        )
    )
    assert value.payload[field] is None
    assert value.payload["availability_notes"][field] == "API field unavailable"
    with pytest.raises(ValueError, match="availability note"):
        camera_view_value(_camera_payload(**{field: None}))


def test_catalogue_table_has_fixed_order_roundtrips_and_keeps_same_names_distinct() -> (
    None
):
    first = _row(
        "object",
        system_key="system-1",
        display_name="Load",
        object_id=1,
        object_path="A/Load",
        selector_code=_selector("object", 1, "A/Load"),
    )
    second = _row(
        "object",
        system_key="system-1",
        display_name="Load",
        object_id=2,
        object_path="B/Load",
        selector_code=_selector("object", 2, "B/Load"),
    )
    table = catalogue_table([_row(), first, second])
    assert table.column_names == CATALOGUE_COLUMNS
    restored = scientific_from_payload(scientific_to_payload(table))
    assert type(restored) is type(table)
    frame = restored.to_pandas()
    assert frame.loc[1:, "display_name"].tolist() == ["Load", "Load"]
    assert frame.loc[1:, "selector_code"].nunique() == 2


def test_catalogue_rejects_wrong_identity_duplicate_selector_and_nested_cells() -> None:
    item = _row(
        "object",
        system_key="system-1",
        object_path="Model/Load",
        selector_code=_selector("object", 1),
        object_id=1,
    )
    with pytest.raises(ValueError, match="run_id must agree"):
        catalogue_table([_row(), {**item, "run_id": "other"}])
    with pytest.raises(ValueError, match="duplicate"):
        catalogue_table([_row(), item, dict(item)])
    with pytest.raises(TypeError, match="display_value"):
        catalogue_table([_row(), {**item, "display_value": {"nested": True}}])
    wrong_kind = {
        **item,
        "selector_code": _selector("property", 1),
    }
    with pytest.raises(ValueError, match="selector kind"):
        catalogue_table([_row(), wrong_kind])


@pytest.mark.parametrize(
    ("kind", "field", "value"),
    [
        ("object", "omitted_rows", 9),
        ("view", "has_tabular_data", True),
        ("property", "view_name", "Front"),
        ("operation", "object_id", 4),
        ("object", "system_label", "System A"),
    ],
)
def test_catalogue_rejects_fields_on_unrelated_row_kinds(
    kind: str, field: str, value: object
) -> None:
    with pytest.raises(ValueError, match=f"{field} is not applicable"):
        catalogue_table([_row(), _row(kind, **{field: value})])


def test_catalogue_requires_one_first_summary_and_canonical_path() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        catalogue_table([_row("operation")])
    with pytest.raises(ValueError, match="canonical JSON"):
        catalogue_table([_row(producer_path="[0, 2]")])
    with pytest.raises(ValueError, match="zero omitted"):
        catalogue_table([_row(omitted_rows=1)])


def test_catalogue_enforces_row_and_encoded_content_bounds(monkeypatch) -> None:
    monkeypatch.setattr(mechanical_contracts, "CATALOGUE_MAX_ROWS", 1)
    with pytest.raises(ValueError, match="100000 rows"):
        catalogue_table([_row(), _row("operation")])
    monkeypatch.setattr(mechanical_contracts, "CATALOGUE_MAX_ROWS", 100_000)
    monkeypatch.setattr(mechanical_contracts, "CATALOGUE_MAX_ENCODED_BYTES", 1)
    with pytest.raises(ValueError, match="64 MiB"):
        catalogue_table([_row()])


def test_definitions_table_uses_fixed_scalar_schema_and_preserves_null_set() -> None:
    row = dict.fromkeys(DEFINITIONS_COLUMNS, "")
    row.update(
        table_index=0, column_index=1, result_set=None, unit="N", definition_kind="free"
    )
    table = definitions_table([row])
    assert table.column_names == DEFINITIONS_COLUMNS
    frame = scientific_from_payload(scientific_to_payload(table)).to_pandas()
    assert pd.isna(frame.loc[0, "result_set"])
    with pytest.raises(ValueError, match="unexpected fields"):
        definitions_table([{**row, "extra": 1}])


def test_catalog_validates_all_carriers_without_ansys_imports() -> None:
    catalog = DataTypeCatalog()
    catalog.register_many(
        families=(MECHANICAL_DATA_TYPE_FAMILY,),
        types=MECHANICAL_DATA_TYPES,
        owner_id="mechanical.corex",
        owner_version="1",
        source_label="test",
    )
    catalog.validate_carrier(OBJECT_TYPE_ID, object_value(_object_payload()))
    catalog.validate_carrier(PROPERTY_TYPE_ID, property_value(_property_payload()))
    catalog.validate_carrier(CAMERA_VIEW_TYPE_ID, camera_view_value(_camera_payload()))


def test_mechanical_backend_registers_all_five_semantic_contracts() -> None:
    registry = build_builtin_registry()
    assert register_plugin_backends(
        (MECHANICAL_PLUGIN_BACKEND,), registry, "mechanical"
    ) == [
        "mechanical.open_model",
        "mechanical.search_tree",
        "mechanical.fea_table",
        "mechanical.camera_views",
        "mechanical.export_image",
        "mechanical.run_script",
        "mechanical.apdl_snippet",
        "mechanical.save_model",
    ]
    assert {
        spec.type_id
        for spec in registry.data_types.all_specs()
        if spec.type_id.startswith("COREX.Mechanical.")
    } == {MODEL_TYPE_ID, OBJECT_TYPE_ID, PROPERTY_TYPE_ID, CAMERA_VIEW_TYPE_ID}
