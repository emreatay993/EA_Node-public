# Telemetry, Help, Benchmarks, Custom Workflows, And Runtime Contracts

## Purpose
Use this for support layers that are not owned by graph, persistence, or UI: telemetry, help, benchmarks, runtime contracts, mockups, and custom workflows.

## Start Here
- `ea_node_editor/runtime_contracts/data_types.py`
- `ea_node_editor/runtime_contracts/scientific_values.py`
- `ea_node_editor/runtime_contracts/scientific_codec.py`
- `ea_node_editor/telemetry/`
- `ea_node_editor/help/`
- `ea_node_editor/benchmarks/`
- `ea_node_editor/runtime_contracts/`
- `ea_node_editor/custom_workflows/`
- `ea_node_editor/mockups/`
- `examples/`
- `scripts/`

## Runtime Contracts

- Solution records retain node-scoped interface provenance; whole-workflow fingerprints remain in execution preparation. Immutable result records and per-port digests stay independent of UI and persistence implementations.

- `runtime_contracts/scientific_values.py` owns immutable ArrayValue/TableValue buffers, dtype/shape validation and isolated native script adapters; SeriesValue is the series TableValue variant. `scientific_codec.py` owns the versioned data-only wire format and 256 MiB/value, 512 MiB/operation decoded-content bounds. Scientific values remain durable-ineligible, and JSON collection validation stays unchanged.
- `runtime_contracts/data_tree.py` owns immutable path-indexed `DataTree` values and modifier ordering.
- `runtime_contracts/image_value.py` owns strict immutable PNG parsing and `ImageValue`; `value_refs.py` owns inline, artifact, and handle carriers; `tabular_data.py` owns tabular and array carriers; `value_codec.py` owns recursive tagged serialization; and `durable_values.py` owns callback-free durable decoding and validation. The durable gate retains declared/concrete catalog checks, assignability, persistence/sensitivity, carrier kinds, per-inline size, artifact metadata, private/staging/session/path rejection, markers, and current managed-artifact integrity.
- `common/artifact_refs.py` owns only the dependency-light `saved://` and `temp://` grammar shared by runtime contracts and persistence.
- `runtime_contracts/data_types.py` owns catalog registration, parent assignability, strongest declared-union compatibility, carrier compatibility, and catalog fingerprints. `DataTypeCompatibility` remains the sole structured relation record; `connection_fallback` is a type capability consumed only by recommendation policy.
- `ea_node_editor/nodes/core_data_types.py` registers bounded exact JSON-domain `COREX.DataTypes.JsonValue` and native `COREX.Plot.ExportBundle`; the latter is an exact four-key dictionary with two artifact refs and two JSON metadata dictionaries, not a JSON-derived type. Any, Json, GraphArray, and GraphDictionary carry the fallback capability.
- `runtime_contracts/interval_1d.py` owns immutable ordered `Interval1D` values and strict coercion.
- `runtime_contracts/settled_results.py` owns immutable settled port/root-error DTOs plus shared DataTree/output/error count and transport limits.
- `runtime_contracts/solution_records.py` owns strict immutable freshness, residency, heterogeneous concrete-type/carrier output descriptors, payload locators, durable logical/record ID bounds, and `reuse_eligible` observation/solution records without importing execution implementation.

## Boundaries
- Keep support ownership explicit; do not move graph, persistence, or UI behavior here.
- Keep generated benchmark outputs under ignored local roots.
- Publish accepted COREX behavior and current verification only.
- Keep `ea_node_editor/common/` dependency-light and free of graph, UI, execution, persistence, and nodes imports.
- Import runtime values from their defining modules or the intentional `runtime_contracts` package surface; do not add another compatibility codec/barrel.

## Focused Tests
- `tests/test_scientific_values.py`
- `tests/test_scientific_worker_transport.py`
- `tests/test_typed_runtime_values.py`
- `tests/test_image_value.py`
- `tests/test_data_type_catalog.py`
- `tests/test_core_value_codecs.py`
- `tests/test_core_value_types.py`
- `tests/test_tree_path_types.py`
- `tests/test_core_media_types.py`
- `tests/test_unit_types.py`
- `tests/test_solution_records.py`

## Focused Verification
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_typed_runtime_values.py tests/test_solution_records.py -q
```
