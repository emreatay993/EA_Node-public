# COREX Solution Reuse Classification

Status: `CLASSIFICATION_DRAFTING` — inventory and policy only; no implementation proof.

This document is the exact shipped-row authority for T02 of
`docs/PLAN_COREX_INCREMENTAL_EXECUTION_AND_SOLUTION_SNAPSHOTS.md`. It classifies
the maximum reuse residency of every shipped registry row before any node metadata
is changed. A declared maximum never guarantees a cache hit: missing identity,
provenance, integrity, codec, environment, or runtime-generation evidence always
downgrades the decision to recomputation.

## Authority Snapshot

| Fact | Value |
| --- | --- |
| Classification schema | `corex.solution_reuse_classification.v1` |
| Base state | T01 accepted working-tree state |
| Base HEAD | `86a5f562e7c5c9d7d52dad97f842a89631508a26` |
| Plan SHA-256 | `4FFFCFC5B23BA1A2E755CE8222F9EE221B3AA108EAC9F63779310EEBF370A47F` |
| Ledger SHA-256 at drafting start | `200388ABF798E86431103DEBD0E94ECF0C584617FC2D15E6499B6A03FA01A21E` |
| Current repo-owned catalog SHA-256 | `89F7ADC2735AFC067874447E732418657DADD9BC81D44D75FD6C38D23825FF4A` |
| Migration inventory SHA-256 | `A5E22F1DD5C0BE9E4BC069E934485EF37E6B78E9EBCEFFD1E35A0A88017FAEC5` |
| Repo-owned type-ID list SHA-256 | `DF2D6AA4042671D987C58C6F6D8AE84E178B1B3BCB81E5E9F3F2CDF4497B1827` |

The catalog hash is the committed JSON file hash. The type-ID hash is over sorted
IDs joined by LF with a final LF.

## Locked Totals

| Classification | Rows |
| --- | ---: |
| `durable` | 29 |
| `session` | 27 |
| `never` | 53 |
| Executable subtotal | 109 |
| Excluded passive | 35 |
| Excluded compile-only | 3 |
| Excluded subtotal | 38 |
| Repo-owned total | 147 |

## Scope Meanings

- `durable`: deterministic portable identity and a durable output codec are
  available. Runtime validation may still downgrade to `session` or `never`.
- `session`: deterministic only within the accepted runtime generation, or the
  result contains a live handle, prepared scene, runtime ref, or a declared output
  without a durable codec.
- `never`: execution is an effect, provenance is incomplete, behavior is
  untrusted or nondeterministic, sensitive state is involved, or hidden mutable
  state is not snapshot-coupled.
- `excluded`: the row is passive or compile-only and never owns a solution record.

## Fail-Closed Precedence

Apply these rules in order; later rules cannot broaden an earlier decision.

1. Passive and compile-only rows are excluded.
2. Runtime-discovered public or otherwise untrusted declarations are `never`.
3. External effects, credentials, remote state, arbitrary code, Trigger state,
   or uncoupled hidden mutable state are `never`.
4. Missing or invalid implementation, environment, interface, catalog,
   provenance, integrity, codec, or runtime-generation evidence is `never`.
5. A session-only input or output caps the row at `session`.
6. `durable` is allowed only when every input fact and output descriptor remains
   portable and codec-valid.
7. The table scope is a maximum. Runtime preparation may downgrade it but must
   never upgrade it.

## Locked Family Rules

| Family | Rows | Maximum | Locked reason |
| --- | ---: | --- | --- |
| Pure scalar/control transforms | 4 | `durable` | Pure implementation and durable catalog codecs. |
| Pure path/interval/unit transforms | 8 | `durable` | Canonical inline values and durable catalog codecs. |
| Pure spatial transforms | 13 | `durable` | Canonical inline geometry values; no live native owner. |
| Viewer viewport transforms | 2 | `durable` | Canonical inline viewport codec. |
| Markdown rendering from session-only input | 1 | `session` | Durable text output is capped by the non-durable flowchart input codec. |
| Plane value container | 1 | `durable` | Canonical inline plane codec. |
| Signal image rendering | 1 | `durable` | Deterministic renderer identity plus validated image digest/codec. |
| File/import readers | 5 | `session` | Content hash, path policy, importer/environment digest; initially session-only. |
| Model Viewer | 1 | `session` | Live viewer handle and transport require exact runtime generation. |
| Geometry/FE/optimization handles | 7 | `session` | Live/native/runtime handles require exact generation validation. |
| Tabular runtime refs | 5 | `session` | Runtime-local refs or declared non-durable materialization codecs. |
| Pure rows with non-durable input/output codecs | 8 | `session` | Deterministic result, but an input or declared output type is not durable. |
| Effect/state families | 37 | `never` | External effect, untracked state, arbitrary code, secrets, or hidden state. |

## Primary Acceptance Chain

`engineering.cad_import` is `session`: its identity requires the source content
SHA-256, normalized path policy, importer/build/environment digest, applicable
artifact semantic identity and current integrity, normalized properties, and a
session-valid prepared-scene result. Timestamp-only identity is forbidden.

`model.viewer` is `session`: its identity requires ordered upstream solution keys,
normalized viewer settings, backend/build/environment identity, and exact live
handle/transport generation validation. Reuse may preserve an accepted live
session; a generation or transport mismatch always recomputes.

## Public Declaration Rule

Every runtime-discovered public/untrusted executable declaration, including every
`custom.*` row, is hard-locked to `never`. Bundle and function source digests prove
content identity but do not prove absence of hidden time, randomness, environment,
network access, callbacks, or side effects. Private public-plugin IDs, source
locations, and package paths are deliberately absent from this tracked artifact.

## Executable Row Inventory

| Type ID | Display name | Runtime | Entry kind | Declaration owner | Owner family | Scope | Side-effect class | Implementation digest source | Input provenance | Output codec/residency | Handle/artifact facts | Reason code | Proving test |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `ai.create_vector_collection` | Create Vector Collection | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/ai_vector_database.py` | AI/Vector Database | `never` | `untracked_external_state` | `not_required_never` | `not_used_never` | `not_reusable` | `none` | `untracked_external_state` | `tests/test_remaining_builtin_function_migration.py` |
| `ai.inspect_vector_collection` | Inspect Vector Collection | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/ai_vector_database.py` | AI/Vector Database | `never` | `untracked_external_state` | `not_required_never` | `not_used_never` | `not_reusable` | `none` | `untracked_external_state` | `tests/test_remaining_builtin_function_migration.py` |
| `ai.large_language_model` | Large Language Model | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/ai_agent.py` | AI/Agent | `never` | `untracked_external_state` | `not_required_never` | `not_used_never` | `not_reusable` | `none` | `untracked_external_state` | `tests/test_remaining_builtin_function_migration.py` |
| `ai.sqlite_vector_database` | SQLite Vector Database | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/ai_vector_database.py` | AI/Vector Database | `never` | `untracked_external_state` | `not_required_never` | `not_used_never` | `not_reusable` | `none` | `untracked_external_state` | `tests/test_remaining_builtin_function_migration.py` |
| `core.constant` | Constant | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/core_value.py` | Core | `session` | `pure` | `core_build+bundle+source` | `canonical_values+ordered_upstream_keys` | `session_declared_codec_never` | `none` | `portable_output_codec_unavailable` | `tests/test_builtin_function_migration.py` |
| `core.if` | If | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/core_value.py` | Core | `session` | `pure` | `core_build+bundle+source` | `canonical_values+ordered_upstream_keys+handle_generation_or_artifact_integrity` | `session_any_output_validated` | `handle_generation+artifact_semantic_identity+current_integrity_as_applicable` | `portable_output_codec_unavailable` | `tests/test_core_value_nodes.py` |
| `core.logger` | Logger | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/core_value.py` | Core | `never` | `diagnostic_effect` | `not_required_never` | `not_used_never` | `not_reusable` | `none` | `external_side_effect` | `tests/test_remaining_builtin_function_migration.py` |
| `core.python_script` | Python Script | `active` | `TrustedFactoryEntry` | `ea_node_editor/nodes/builtins/core.py` | Core | `never` | `untrusted_user_code` | `not_required_never` | `not_used_never` | `not_reusable` | `none` | `user_code_untrusted` | `tests/test_python_script_declaration.py` |
| `core.stream_gate` | Stream Gate | `active` | `TrustedFactoryEntry` | `ea_node_editor/nodes/builtins/core.py` | Core | `never` | `stateful_control` | `not_required_never` | `not_used_never` | `not_reusable` | `none` | `trigger_publication_not_snapshot` | `tests/test_core_dataflow_nodes.py` |
| `core.trigger` | Trigger | `active` | `TrustedFactoryEntry` | `ea_node_editor/nodes/builtins/core.py` | Data/Control | `never` | `stateful_control` | `not_required_never` | `not_used_never` | `not_reusable` | `none` | `trigger_publication_not_snapshot` | `tests/test_trigger_node.py` |
| `data.boolean_toggle` | Boolean Toggle | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/data_control.py` | Data/Control | `durable` | `pure` | `core_build+bundle+source` | `canonical_values+ordered_upstream_keys` | `durable_catalog_codec` | `none` | `pure_portable_codec` | `tests/test_boolean_toggle_node.py` |
| `data.construct_path` | Construct Path | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/unit_math.py` | Data Structure/Tree | `durable` | `pure` | `core_build+bundle+source` | `canonical_values+ordered_upstream_keys` | `durable_catalog_codec` | `none` | `pure_portable_codec` | `tests/test_core_unit_nodes.py` |
| `data.deconstruct_color` | Deconstruct Color | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/core_value.py` | Utilities/Color | `durable` | `pure` | `core_build+bundle+source` | `canonical_values+ordered_upstream_keys` | `durable_catalog_codec` | `none` | `pure_portable_codec` | `tests/test_core_value_nodes.py` |
| `data.deconstruct_path` | Deconstruct Path | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/unit_math.py` | Data Structure/Tree | `durable` | `pure` | `core_build+bundle+source` | `canonical_values+ordered_upstream_keys` | `durable_catalog_codec` | `none` | `pure_portable_codec` | `tests/test_core_unit_nodes.py` |
| `data.excel_cell` | Excel Cell | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/unit_math.py` | Data/Excel | `session` | `pure` | `core_build+bundle+source` | `canonical_values+ordered_upstream_keys` | `session_declared_codec_never` | `none` | `portable_output_codec_unavailable` | `tests/test_core_unit_nodes.py` |
| `data.number_slider` | Number Slider | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/data_control.py` | Data/Control | `durable` | `pure` | `core_build+bundle+source` | `canonical_values+ordered_upstream_keys` | `durable_catalog_codec` | `none` | `pure_portable_codec` | `tests/test_number_slider_node.py` |
| `data.panel` | Panel | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/data_control.py` | Data/Control | `session` | `pure` | `core_build+bundle+source` | `canonical_values+ordered_upstream_keys+handle_generation_or_artifact_integrity` | `session_any_output_validated` | `handle_generation+artifact_semantic_identity+current_integrity_as_applicable` | `portable_output_codec_unavailable` | `tests/test_panel_node.py` |
| `data.select` | Select | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/data_control.py` | Data/Control | `durable` | `pure` | `core_build+bundle+source` | `canonical_values+ordered_upstream_keys` | `durable_catalog_codec` | `none` | `pure_portable_codec` | `tests/test_select_node.py` |
| `engineering.cad_import` | CAD Import | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/engineering_imports.py` | Engineering/Import | `session` | `read_only_external` | `core_build+bundle+source` | `file_sha256+path_policy+environment_digest+artifact_semantic_identity+current_integrity` | `session_prepared_scene` | `prepared_scene_runtime_generation+artifact_semantic_identity+current_integrity` | `external_file_reader_session_only` | `tests/test_engineering_import_nodes.py` |
| `engineering.fe_import` | FE Import | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/engineering_imports.py` | Engineering/Import | `session` | `read_only_external` | `core_build+bundle+source` | `file_sha256+path_policy+environment_digest+artifact_semantic_identity+current_integrity` | `session_prepared_scene` | `prepared_scene_runtime_generation+artifact_semantic_identity+current_integrity` | `external_file_reader_session_only` | `tests/test_engineering_import_nodes.py` |
| `fea.force` | Force | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/engineering_fem.py` | FEA/Loads | `session` | `pure_runtime_local` | `core_build+bundle+source` | `canonical_values+ordered_upstream_keys+handle_generation` | `session_runtime_handle_or_inline` | `live_handle_generation` | `runtime_handle_generation_bound` | `tests/test_fem_contracts.py` |
| `fea.load_container` | Load Container | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/engineering_fem.py` | FEA/Loads | `session` | `pure_runtime_local` | `core_build+bundle+source` | `canonical_values+ordered_upstream_keys+handle_generation` | `session_runtime_handle_or_inline` | `live_handle_generation` | `runtime_handle_generation_bound` | `tests/test_fem_contracts.py` |
| `geometry.chain_transforms` | Chain Transforms | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/spatial.py` | Geometry/Transform | `durable` | `pure` | `core_build+bundle+source` | `canonical_values+ordered_upstream_keys` | `durable_catalog_codec` | `none` | `pure_portable_codec` | `tests/test_spatial_values.py` |
| `geometry.construct_group` | Construct Geometry Group | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/engineering_geometry.py` | Geometry/Model | `session` | `pure_runtime_local` | `core_build+bundle+source` | `canonical_values+ordered_upstream_keys+handle_generation` | `session_runtime_handle_or_inline` | `live_handle_generation` | `runtime_handle_generation_bound` | `tests/test_geometry_primitives.py` |
| `geometry.construct_transform` | Construct Transform | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/spatial.py` | Geometry/Transform | `durable` | `pure` | `core_build+bundle+source` | `canonical_values+ordered_upstream_keys` | `durable_catalog_codec` | `none` | `pure_portable_codec` | `tests/test_transform3d.py` |
| `geometry.cylinder` | Cylinder | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/engineering_geometry.py` | Geometry/Primitive | `session` | `pure_runtime_local` | `core_build+bundle+source` | `canonical_values+ordered_upstream_keys+handle_generation` | `session_runtime_handle_or_inline` | `live_handle_generation` | `runtime_handle_generation_bound` | `tests/test_geometry_primitives.py` |
| `geometry.deconstruct_transform` | Deconstruct Transform | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/spatial.py` | Geometry/Transform | `durable` | `pure` | `core_build+bundle+source` | `canonical_values+ordered_upstream_keys` | `durable_catalog_codec` | `none` | `pure_portable_codec` | `tests/test_transform3d.py` |
| `geometry.unchain_transforms` | Unchain Transforms | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/spatial.py` | Geometry/Transform | `durable` | `pure` | `core_build+bundle+source` | `canonical_values+ordered_upstream_keys` | `durable_catalog_codec` | `none` | `pure_portable_codec` | `tests/test_spatial_values.py` |
| `io.email_send` | Email Send | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/integrations_email.py` | Input / Output | `never` | `external_side_effect` | `not_required_never` | `not_used_never` | `not_reusable` | `external_output_or_effect` | `external_side_effect` | `tests/test_builtin_integration_function_migration.py` |
| `io.excel_read` | Excel Read | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/integrations_spreadsheet.py` | Input / Output | `session` | `read_only_external` | `core_build+bundle+source` | `file_sha256+path_policy+environment_digest+artifact_semantic_identity+current_integrity` | `session_declared_codec_never` | `artifact_semantic_identity+current_integrity` | `external_file_reader_session_only` | `tests/test_builtin_integration_function_migration.py` |
| `io.excel_write` | Excel Write | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/integrations_spreadsheet.py` | Input / Output | `never` | `external_side_effect` | `not_required_never` | `not_used_never` | `not_reusable` | `external_output_or_effect` | `external_side_effect` | `tests/test_builtin_integration_function_migration.py` |
| `io.file_read` | File Read | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/integrations_file_io.py` | Input / Output | `session` | `read_only_external` | `core_build+bundle+source` | `file_sha256+path_policy+environment_digest+artifact_semantic_identity+current_integrity` | `session_inline_text` | `artifact_semantic_identity+current_integrity` | `external_file_reader_session_only` | `tests/test_builtin_integration_function_migration.py` |
| `io.file_write` | File Write | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/integrations_file_io.py` | Input / Output | `never` | `external_side_effect` | `not_required_never` | `not_used_never` | `not_reusable` | `external_output_or_effect` | `external_side_effect` | `tests/test_builtin_integration_function_migration.py` |
| `io.combine_file_paths` | Combine File Paths | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/filesystem.py` | Utilities/File System | `never` | `host_filesystem_path_rules` | `not_required_never` | `not_used_never` | `not_reusable` | `host_path_semantics` | `filesystem_environment` | `tests/test_filesystem_function_nodes.py` |
| `io.construct_file_path` | Construct File Path | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/filesystem.py` | Utilities/File System | `never` | `host_filesystem_path_rules` | `not_required_never` | `not_used_never` | `not_reusable` | `host_path_semantics` | `filesystem_environment` | `tests/test_filesystem_function_nodes.py` |
| `io.contents_in_directory` | Contents in Directory | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/filesystem.py` | Utilities/File System | `never` | `read_only_external` | `not_required_never` | `not_used_never` | `not_reusable` | `external_file_listing` | `filesystem_environment` | `tests/test_filesystem_function_nodes.py` |
| `io.create_directory` | Create Directory | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/filesystem.py` | Utilities/File System | `never` | `external_side_effect` | `not_required_never` | `not_used_never` | `not_reusable` | `external_output_or_effect` | `external_side_effect` | `tests/test_filesystem_function_nodes.py` |
| `io.deconstruct_file_path` | Deconstruct File Path | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/filesystem.py` | Utilities/File System | `never` | `host_filesystem_path_rules` | `not_required_never` | `not_used_never` | `not_reusable` | `host_path_semantics` | `filesystem_environment` | `tests/test_filesystem_function_nodes.py` |
| `io.delete_file` | Delete File | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/filesystem.py` | Utilities/File System | `never` | `external_side_effect` | `not_required_never` | `not_used_never` | `not_reusable` | `external_output_or_effect` | `external_side_effect` | `tests/test_filesystem_function_nodes.py` |
| `io.move_file` | Move File | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/filesystem.py` | Utilities/File System | `never` | `external_side_effect` | `not_required_never` | `not_used_never` | `not_reusable` | `external_output_or_effect` | `external_side_effect` | `tests/test_filesystem_function_nodes.py` |
| `io.temporary_file_path` | Temporary File Path | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/filesystem.py` | Utilities/File System | `never` | `host_filesystem_path_rules` | `not_required_never` | `not_used_never` | `not_reusable` | `host_path_semantics` | `filesystem_environment` | `tests/test_filesystem_function_nodes.py` |
| `io.image_export` | Export Image | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/integrations_file_io.py` | Input / Output | `never` | `external_side_effect` | `not_required_never` | `not_used_never` | `not_reusable` | `external_output_or_effect` | `external_side_effect` | `tests/test_builtin_integration_function_migration.py` |
| `io.image_import` | Import Image | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/integrations_file_io.py` | Input / Output | `session` | `read_only_external` | `core_build+bundle+source` | `file_sha256+path_policy+environment_digest+artifact_semantic_identity+current_integrity` | `session_inline_image` | `artifact_semantic_identity+current_integrity` | `external_file_reader_session_only` | `tests/test_signal_plot_renderer.py` |
| `io.process_run` | Process Run | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/integrations_process.py` | Input / Output | `never` | `external_side_effect` | `not_required_never` | `not_used_never` | `not_reusable` | `external_output_or_effect` | `external_side_effect` | `tests/test_builtin_integration_function_migration.py` |
| `mars.batch_solve` | MARS Batch Solve | `active` | `PythonFunctionEntry` | `ea_node_editor/addons/mars/function_nodes.py` | MARS | `never` | `external_toolchain_effect` | `not_required_never` | `not_used_never` | `not_reusable` | `managed_artifact_effect` | `external_side_effect` | `tests/test_mars_function_migration.py` |
| `mars.run_job` | MARS Run Job | `active` | `PythonFunctionEntry` | `ea_node_editor/addons/mars/function_nodes.py` | MARS | `never` | `external_toolchain_effect` | `not_required_never` | `not_used_never` | `not_reusable` | `managed_artifact_effect` | `external_side_effect` | `tests/test_mars_function_migration.py` |
| `mars.time_history` | MARS Time History | `active` | `PythonFunctionEntry` | `ea_node_editor/addons/mars/function_nodes.py` | MARS | `never` | `external_toolchain_effect` | `not_required_never` | `not_used_never` | `not_reusable` | `managed_artifact_effect` | `external_side_effect` | `tests/test_mars_function_migration.py` |
| `mechanical.apdl_snippet` | Mechanical APDL Snippet | `active` | `PythonFunctionEntry` | `ea_node_editor/addons/mechanical/function_nodes.py` | FEA | `never` | `external_side_effect` | `not_required_never` | `not_used_never` | `not_reusable` | `run_owned_native_session` | `external_side_effect` | `tests/mechanical_catalogue/test_snippets.py` |
| `mechanical.camera_views` | Mechanical Camera Views | `active` | `PythonFunctionEntry` | `ea_node_editor/addons/mechanical/function_nodes.py` | FEA | `never` | `read_only_external` | `not_required_never` | `not_used_never` | `not_reusable` | `run_owned_native_session` | `runtime_handle_generation_bound` | `tests/mechanical_catalogue/test_camera_views.py` |
| `mechanical.export_image` | Export Mechanical Image | `active` | `PythonFunctionEntry` | `ea_node_editor/addons/mechanical/function_nodes.py` | FEA | `never` | `external_side_effect` | `not_required_never` | `not_used_never` | `not_reusable` | `external_output_or_effect` | `external_side_effect` | `tests/mechanical_catalogue/test_image_export.py` |
| `mechanical.fea_table` | FEA Table | `active` | `PythonFunctionEntry` | `ea_node_editor/addons/mechanical/function_nodes.py` | FEA | `never` | `read_only_external` | `not_required_never` | `not_used_never` | `not_reusable` | `run_owned_native_session` | `runtime_handle_generation_bound` | `tests/mechanical_catalogue/test_definition_tables.py` |
| `mechanical.open_model` | Open Mechanical Model | `active` | `PythonFunctionEntry` | `ea_node_editor/addons/mechanical/function_nodes.py` | FEA | `never` | `read_only_external` | `not_required_never` | `not_used_never` | `not_reusable` | `run_owned_native_session` | `runtime_handle_generation_bound` | `tests/mechanical_catalogue/test_catalogue.py` |
| `mechanical.run_script` | Run Mechanical Script | `active` | `PythonFunctionEntry` | `ea_node_editor/addons/mechanical/function_nodes.py` | FEA | `never` | `external_side_effect` | `not_required_never` | `not_used_never` | `not_reusable` | `run_owned_native_session` | `external_side_effect` | `tests/mechanical_catalogue/test_scripts.py` |
| `mechanical.save_model` | Save Mechanical Model | `active` | `PythonFunctionEntry` | `ea_node_editor/addons/mechanical/function_nodes.py` | FEA | `never` | `external_side_effect` | `not_required_never` | `not_used_never` | `not_reusable` | `external_output_or_effect` | `external_side_effect` | `tests/mechanical_catalogue/test_standalone_save.py` |
| `mechanical.search_tree` | Search Mechanical Tree | `active` | `PythonFunctionEntry` | `ea_node_editor/addons/mechanical/function_nodes.py` | FEA | `never` | `read_only_external` | `not_required_never` | `not_used_never` | `not_reusable` | `run_owned_native_session` | `runtime_handle_generation_bound` | `tests/mechanical_catalogue/test_search_tree.py` |
| `math.bounding_interval_2d` | Bounding Interval 2D | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/spatial.py` | Math/Interval | `durable` | `pure` | `core_build+bundle+source` | `canonical_values+ordered_upstream_keys` | `durable_catalog_codec` | `none` | `pure_portable_codec` | `tests/test_spatial_values.py` |
| `math.construct_interval` | Construct Interval | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/unit_math.py` | Math/Interval | `durable` | `pure` | `core_build+bundle+source` | `canonical_values+ordered_upstream_keys` | `durable_catalog_codec` | `none` | `pure_portable_codec` | `tests/test_interval_nodes.py` |
| `math.deconstruct_interval` | Deconstruct Interval | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/unit_math.py` | Math/Interval | `durable` | `pure` | `core_build+bundle+source` | `canonical_values+ordered_upstream_keys` | `durable_catalog_codec` | `none` | `pure_portable_codec` | `tests/test_interval_nodes.py` |
| `math.deconstruct_interval_2d` | Deconstruct Interval 2D | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/unit_math.py` | Math/Interval | `durable` | `pure` | `core_build+bundle+source` | `canonical_values+ordered_upstream_keys` | `durable_catalog_codec` | `none` | `pure_portable_codec` | `tests/test_core_unit_nodes.py` |
| `math.deconstruct_tensor` | Deconstruct Tensor | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/unit_math.py` | Math/Tensor | `durable` | `pure` | `core_build+bundle+source` | `canonical_values+ordered_upstream_keys` | `durable_catalog_codec` | `none` | `pure_portable_codec` | `tests/test_core_unit_nodes.py` |
| `math.field_vector_container` | Field Vector | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/spatial.py` | Math/Container | `session` | `pure` | `core_build+bundle+source` | `canonical_values+ordered_upstream_keys` | `session_declared_codec_never` | `none` | `portable_output_codec_unavailable` | `tests/test_spatial_values.py` |
| `math.physical_quantity_container` | Physical Quantity | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/unit_math.py` | Math/Container | `session` | `pure` | `core_build+bundle+source` | `canonical_values+ordered_upstream_keys` | `session_declared_codec_never` | `none` | `portable_output_codec_unavailable` | `tests/test_core_unit_nodes.py` |
| `math.unit_system_container` | Unit System | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/unit_math.py` | Math/Container | `durable` | `pure` | `core_build+bundle+source` | `canonical_values+ordered_upstream_keys` | `durable_catalog_codec` | `none` | `pure_portable_codec` | `tests/test_core_unit_nodes.py` |
| `media.panel` | Media Panel | `active` | `TrustedFactoryEntry` | `ea_node_editor/nodes/builtins/media_panel.py` | Media | `never` | `display_or_network_state` | `not_required_never` | `not_used_never` | `not_reusable` | `none` | `display_or_network_state` | `tests/test_media_panel.py` |
| `mesh.deconstruct_mesh_face` | Deconstruct Mesh Face | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/engineering_geometry.py` | Mesh/Analyse | `session` | `pure` | `core_build+bundle+source` | `non_durable_inline_mesh_face+ordered_upstream_keys` | `durable_integer_outputs+session_input_cap` | `none` | `portable_input_codec_unavailable` | `tests/test_mesh_contracts.py` |
| `model.viewer` | Model Viewer | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/engineering_viewer.py` | Engineering/Viewer | `session` | `runtime_local_state` | `core_build+bundle+source` | `ordered_upstream_keys+viewer_environment` | `session_viewer_handle+inline_selection` | `live_handle+transport_generation` | `runtime_handle_generation_bound` | `tests/test_engineering_viewer_node.py` |
| `optimization.construct_design` | Construct Design | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/engineering_fem.py` | Control/Parameter Optimization | `session` | `pure_runtime_local` | `core_build+bundle+source` | `canonical_values+ordered_upstream_keys+handle_generation` | `session_runtime_handle_or_inline` | `live_handle_generation` | `runtime_handle_generation_bound` | `tests/test_fem_contracts.py` |
| `optimization.construct_parameters` | Construct Parameters | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/engineering_fem.py` | Optimization | `session` | `pure_runtime_local` | `core_build+bundle+source` | `canonical_values+ordered_upstream_keys+handle_generation` | `session_runtime_handle_or_inline` | `live_handle_generation` | `runtime_handle_generation_bound` | `tests/test_fem_contracts.py` |
| `optimization.construct_responses` | Construct Responses | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/engineering_fem.py` | Optimization | `session` | `pure_runtime_local` | `core_build+bundle+source` | `canonical_values+ordered_upstream_keys+handle_generation` | `session_runtime_handle_or_inline` | `live_handle_generation` | `runtime_handle_generation_bound` | `tests/test_fem_contracts.py` |
| `optimization.parameter_pool` | Parameter Pool | `active` | `TrustedFactoryEntry` | `ea_node_editor/nodes/builtins/fem_contracts.py` | Control/Parameter Optimization | `never` | `hidden_mutable_state` | `not_required_never` | `not_used_never` | `not_reusable` | `coupled_worker_state` | `hidden_mutable_worker_state` | `tests/test_parameter_setup_pool_links.py` |
| `optimization.parameter_setup` | Parameter Setup | `active` | `TrustedFactoryEntry` | `ea_node_editor/nodes/builtins/fem_contracts.py` | Control/Parameter Optimization | `never` | `hidden_mutable_state` | `not_required_never` | `not_used_never` | `not_reusable` | `coupled_worker_state` | `hidden_mutable_worker_state` | `tests/test_parameter_setup_pool_links.py` |
| `optimization.response_pool` | Response Pool | `active` | `TrustedFactoryEntry` | `ea_node_editor/nodes/builtins/fem_contracts.py` | Control/Parameter Optimization | `never` | `hidden_mutable_state` | `not_required_never` | `not_used_never` | `not_reusable` | `coupled_worker_state` | `hidden_mutable_worker_state` | `tests/test_parameter_setup_pool_links.py` |
| `plot.bar` | Bar Plot | `active` | `TrustedFactoryEntry` | `ea_node_editor/nodes/builtins/plot/generic.py` | Plot | `never` | `export_or_view_effect` | `not_required_never` | `not_used_never` | `not_reusable` | `managed_artifact_effect` | `external_side_effect` | `tests/test_plot_node_contracts.py` |
| `plot.contour` | Contour Plot | `active` | `TrustedFactoryEntry` | `ea_node_editor/nodes/builtins/plot/generic.py` | Plot | `never` | `export_or_view_effect` | `not_required_never` | `not_used_never` | `not_reusable` | `managed_artifact_effect` | `external_side_effect` | `tests/test_plot_node_contracts.py` |
| `plot.heatmap` | Heatmap Plot | `active` | `TrustedFactoryEntry` | `ea_node_editor/nodes/builtins/plot/generic.py` | Plot | `never` | `export_or_view_effect` | `not_required_never` | `not_used_never` | `not_reusable` | `managed_artifact_effect` | `external_side_effect` | `tests/test_plot_node_contracts.py` |
| `plot.histogram` | Histogram Plot | `active` | `TrustedFactoryEntry` | `ea_node_editor/nodes/builtins/plot/generic.py` | Plot | `never` | `export_or_view_effect` | `not_required_never` | `not_used_never` | `not_reusable` | `managed_artifact_effect` | `external_side_effect` | `tests/test_plot_node_contracts.py` |
| `plot.point_cloud` | Point Cloud Plot | `active` | `TrustedFactoryEntry` | `ea_node_editor/nodes/builtins/plot/generic.py` | Plot | `never` | `export_or_view_effect` | `not_required_never` | `not_used_never` | `not_reusable` | `managed_artifact_effect` | `external_side_effect` | `tests/test_plot_node_contracts.py` |
| `plot.scatter` | Scatter Plot | `active` | `TrustedFactoryEntry` | `ea_node_editor/nodes/builtins/plot/generic.py` | Plot | `never` | `export_or_view_effect` | `not_required_never` | `not_used_never` | `not_reusable` | `managed_artifact_effect` | `external_side_effect` | `tests/test_plot_node_contracts.py` |
| `plot.signal` | Signal Plot | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/plot_signal.py` | Plot | `durable` | `pure` | `core_build+bundle+source` | `canonical_values+ordered_upstream_keys` | `durable_catalog_codec` | `inline_image_sha256` | `pure_portable_codec` | `tests/test_signal_plot_renderer.py` |
| `plot.streamlines` | Streamlines Plot | `active` | `TrustedFactoryEntry` | `ea_node_editor/nodes/builtins/plot/generic.py` | Plot | `never` | `export_or_view_effect` | `not_required_never` | `not_used_never` | `not_reusable` | `managed_artifact_effect` | `external_side_effect` | `tests/test_plot_node_contracts.py` |
| `plot.surface` | Surface Plot | `active` | `TrustedFactoryEntry` | `ea_node_editor/nodes/builtins/plot/generic.py` | Plot | `never` | `export_or_view_effect` | `not_required_never` | `not_used_never` | `not_reusable` | `managed_artifact_effect` | `external_side_effect` | `tests/test_plot_node_contracts.py` |
| `reference.construct_plane` | Construct Plane | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/spatial.py` | Reference/Plane | `durable` | `pure` | `core_build+bundle+source` | `canonical_values+ordered_upstream_keys` | `durable_catalog_codec` | `none` | `pure_portable_codec` | `tests/test_spatial_values.py` |
| `reference.construct_point` | Construct Point | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/spatial.py` | Reference/Point | `durable` | `pure` | `core_build+bundle+source` | `canonical_values+ordered_upstream_keys` | `durable_catalog_codec` | `none` | `pure_portable_codec` | `tests/test_spatial_values.py` |
| `reference.construct_vector` | Construct Vector | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/spatial.py` | Reference/Vector | `durable` | `pure` | `core_build+bundle+source` | `canonical_values+ordered_upstream_keys` | `durable_catalog_codec` | `none` | `pure_portable_codec` | `tests/test_spatial_values.py` |
| `reference.deconstruct_point` | Deconstruct Point | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/spatial.py` | Reference/Point | `durable` | `pure` | `core_build+bundle+source` | `canonical_values+ordered_upstream_keys` | `durable_catalog_codec` | `none` | `pure_portable_codec` | `tests/test_spatial_values.py` |
| `reference.deconstruct_vector` | Deconstruct Vector | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/spatial.py` | Reference/Vector | `durable` | `pure` | `core_build+bundle+source` | `canonical_values+ordered_upstream_keys` | `durable_catalog_codec` | `none` | `pure_portable_codec` | `tests/test_spatial_values.py` |
| `reference.plane_container` | Plane | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/rich_values.py` | Reference/Container | `durable` | `pure` | `core_build+bundle+source` | `canonical_values+ordered_upstream_keys` | `durable_catalog_codec` | `none` | `pure_portable_codec` | `tests/test_rich_values.py` |
| `reference.reverse_vector` | Reverse Vector | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/spatial.py` | Reference/Vector | `durable` | `pure` | `core_build+bundle+source` | `canonical_values+ordered_upstream_keys` | `durable_catalog_codec` | `none` | `pure_portable_codec` | `tests/test_spatial_values.py` |
| `reference.vector_length` | Vector Length | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/spatial.py` | Reference/Vector | `durable` | `pure` | `core_build+bundle+source` | `canonical_values+ordered_upstream_keys` | `durable_catalog_codec` | `none` | `pure_portable_codec` | `tests/test_spatial_values.py` |
| `reference.xy_plane` | XY Plane | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/spatial.py` | Reference/Plane | `durable` | `pure` | `core_build+bundle+source` | `canonical_values+ordered_upstream_keys` | `durable_catalog_codec` | `none` | `pure_portable_codec` | `tests/test_spatial_values.py` |
| `reporting.markdown_flowchart` | Markdown Flowchart | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/reporting.py` | Utilities/Reporting | `session` | `pure` | `core_build+bundle+source` | `non_durable_flowchart_input+ordered_upstream_keys` | `durable_string_output+session_input_cap` | `none` | `portable_input_codec_unavailable` | `tests/test_reporting_nodes.py` |
| `reporting.markdown_flowchart_node` | Markdown Flowchart Node | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/reporting.py` | Utilities/Reporting | `session` | `pure` | `core_build+bundle+source` | `canonical_values+ordered_upstream_keys` | `session_declared_codec_never` | `none` | `portable_output_codec_unavailable` | `tests/test_reporting_nodes.py` |
| `security.windows_authentication` | Windows Authentication | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/security.py` | Security | `never` | `secret_identity_or_remote_effect` | `not_required_never` | `not_used_never` | `not_reusable` | `secret_or_remote_handle` | `secret_or_identity_state` | `tests/test_remaining_builtin_function_migration.py` |
| `ssh_sftp.download` | SFTP Download | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/integrations_ssh_sftp.py` | Control/SSH/SFTP | `never` | `secret_identity_or_remote_effect` | `not_required_never` | `not_used_never` | `not_reusable` | `secret_or_remote_handle` | `external_side_effect` | `tests/test_builtin_integration_function_migration.py` |
| `ssh_sftp.host` | SSH/SFTP Host | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/integrations_ssh_sftp.py` | Control/SSH/SFTP | `never` | `secret_identity_or_remote_effect` | `not_required_never` | `not_used_never` | `not_reusable` | `secret_or_remote_handle` | `secret_or_identity_state` | `tests/test_builtin_integration_function_migration.py` |
| `ssh_sftp.run_command` | Run SSH Command | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/integrations_ssh_sftp.py` | Control/SSH/SFTP | `never` | `secret_identity_or_remote_effect` | `not_required_never` | `not_used_never` | `not_reusable` | `secret_or_remote_handle` | `external_side_effect` | `tests/test_builtin_integration_function_migration.py` |
| `ssh_sftp.run_script` | Run SSH Script | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/integrations_ssh_sftp.py` | Control/SSH/SFTP | `never` | `secret_identity_or_remote_effect` | `not_required_never` | `not_used_never` | `not_reusable` | `secret_or_remote_handle` | `external_side_effect` | `tests/test_builtin_integration_function_migration.py` |
| `ssh_sftp.secret` | Secret | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/integrations_ssh_sftp.py` | Control/SSH/SFTP | `never` | `secret_identity_or_remote_effect` | `not_required_never` | `not_used_never` | `not_reusable` | `secret_or_remote_handle` | `secret_or_identity_state` | `tests/test_builtin_integration_function_migration.py` |
| `ssh_sftp.upload` | SFTP Upload | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/integrations_ssh_sftp.py` | Control/SSH/SFTP | `never` | `secret_identity_or_remote_effect` | `not_required_never` | `not_used_never` | `not_reusable` | `secret_or_remote_handle` | `external_side_effect` | `tests/test_builtin_integration_function_migration.py` |
| `tabular.array_slice_2d` | Array Slice 2D | `active` | `PythonFunctionEntry` | `ea_node_editor/addons/tabular_data/function_nodes.py` | Data | `session` | `pure_runtime_local` | `core_build+addon_bundle+source+owner_version` | `source_sha256+ordered_upstream_keys+runtime_ref_identity` | `session_runtime_ref_or_declared_codec_never` | `runtime_ref_generation` | `runtime_ref_generation_bound` | `tests/test_tabular_function_migration.py` |
| `tabular.input` | Tabular Data Input | `active` | `PythonFunctionEntry` | `ea_node_editor/addons/tabular_data/function_nodes.py` | Data | `session` | `read_only_external` | `core_build+addon_bundle+source+owner_version` | `file_sha256+path_policy+environment_digest+importer_digest+artifact_semantic_identity+current_integrity+runtime_ref_identity` | `session_runtime_ref_or_declared_codec_never` | `runtime_ref_generation+artifact_semantic_identity+current_integrity` | `runtime_ref_generation_bound` | `tests/test_tabular_function_migration.py` |
| `tabular.materialize_array_slice_2d` | Materialize Array Slice 2D | `active` | `PythonFunctionEntry` | `ea_node_editor/addons/tabular_data/function_nodes.py` | Data | `session` | `pure_runtime_local` | `core_build+addon_bundle+source+owner_version` | `source_sha256+ordered_upstream_keys+runtime_ref_identity` | `session_runtime_ref_or_declared_codec_never` | `runtime_ref_generation` | `runtime_ref_generation_bound` | `tests/test_tabular_function_migration.py` |
| `tabular.materialize_table_filter` | Materialize Filtered Table | `active` | `PythonFunctionEntry` | `ea_node_editor/addons/tabular_data/function_nodes.py` | Data | `session` | `pure_runtime_local` | `core_build+addon_bundle+source+owner_version` | `source_sha256+ordered_upstream_keys+runtime_ref_identity` | `session_runtime_ref_or_declared_codec_never` | `runtime_ref_generation` | `runtime_ref_generation_bound` | `tests/test_tabular_function_migration.py` |
| `tabular.table_filter` | Table Filter | `active` | `PythonFunctionEntry` | `ea_node_editor/addons/tabular_data/function_nodes.py` | Data | `session` | `pure_runtime_local` | `core_build+addon_bundle+source+owner_version` | `source_sha256+ordered_upstream_keys+runtime_ref_identity` | `session_runtime_ref_or_declared_codec_never` | `runtime_ref_generation` | `runtime_ref_generation_bound` | `tests/test_tabular_function_migration.py` |
| `tabular.write_array_slice_2d` | Write Array Slice 2D | `active` | `PythonFunctionEntry` | `ea_node_editor/addons/tabular_data/function_nodes.py` | Data | `never` | `external_side_effect` | `not_required_never` | `not_used_never` | `not_reusable` | `external_output_or_effect` | `external_side_effect` | `tests/test_tabular_function_migration.py` |
| `tabular.write_table_filter` | Write Filtered Table | `active` | `PythonFunctionEntry` | `ea_node_editor/addons/tabular_data/function_nodes.py` | Data | `never` | `external_side_effect` | `not_required_never` | `not_used_never` | `not_reusable` | `external_output_or_effect` | `external_side_effect` | `tests/test_tabular_function_migration.py` |
| `utilities.construct_view` | Construct View | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/viewer_viewport.py` | Utilities/Viewer | `durable` | `pure` | `core_build+bundle+source` | `canonical_values+ordered_upstream_keys` | `durable_catalog_codec` | `none` | `pure_portable_codec` | `tests/test_viewer_viewport.py` |
| `utilities.deconstruct_date_time` | Deconstruct Date and Time | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/unit_math.py` | Utilities/Time | `durable` | `pure` | `core_build+bundle+source` | `canonical_values+ordered_upstream_keys` | `durable_catalog_codec` | `none` | `pure_portable_codec` | `tests/test_core_unit_nodes.py` |
| `utilities.deconstruct_view` | Deconstruct View | `active` | `PythonFunctionEntry` | `ea_node_editor/nodes/builtin_functions/viewer_viewport.py` | Utilities/Viewer | `durable` | `pure` | `core_build+bundle+source` | `canonical_values+ordered_upstream_keys` | `durable_catalog_codec` | `none` | `pure_portable_codec` | `tests/test_viewer_viewport.py` |

## Excluded Row Inventory

These rows are present in the shipped registry but do not execute as solution
owners. Their future `NodeTypeSpec.solution_reuse_scope` default remains `never`;
the scheduler excludes them before solution-record classification.

| Type ID | Display name | Runtime | Entry kind | Declaration owner | Exclusion reason | Proving test |
| --- | --- | --- | --- | --- | --- | --- |
| `code.jupyter_notebook` | Jupyter Notebook | `passive` | `TrustedFactoryEntry` | `ea_node_editor/nodes/builtins/jupyter_notebook.py` | `passive_display_only` | `tests/test_jupyter_notebook_node.py` |
| `core.subnode` | Subnode | `compile_only` | `TrustedFactoryEntry` | `ea_node_editor/nodes/builtins/subnode.py` | `compile_only_flattened_before_execution` | `tests/test_dataflow_graph_persistence.py` |
| `core.subnode_input` | Subnode Input | `compile_only` | `TrustedFactoryEntry` | `ea_node_editor/nodes/builtins/subnode.py` | `compile_only_flattened_before_execution` | `tests/test_dataflow_graph_persistence.py` |
| `core.subnode_output` | Subnode Output | `compile_only` | `TrustedFactoryEntry` | `ea_node_editor/nodes/builtins/subnode.py` | `compile_only_flattened_before_execution` | `tests/test_dataflow_graph_persistence.py` |
| `excalidraw.board` | Excalidraw Board | `passive` | `TrustedFactoryEntry` | `ea_node_editor/nodes/builtins/excalidraw.py` | `passive_display_only` | `tests/test_corex_web_host_assets.py` |
| `io.folder_explorer` | Folder Explorer | `passive` | `TrustedFactoryEntry` | `ea_node_editor/nodes/builtins/integrations_file_io.py` | `passive_display_only` | `tests/test_folder_explorer_filesystem_service.py` |
| `io.path_pointer` | Path Pointer | `passive` | `TrustedFactoryEntry` | `ea_node_editor/nodes/builtins/integrations_file_io.py` | `passive_display_only` | `tests/test_passive_runtime_wiring.py` |
| `passive.annotation.callout` | Callout | `passive` | `TrustedFactoryEntry` | `ea_node_editor/nodes/builtins/passive_annotation.py` | `passive_display_only` | `tests/test_passive_node_contracts.py` |
| `passive.annotation.group_backdrop` | Group | `passive` | `TrustedFactoryEntry` | `ea_node_editor/nodes/builtins/passive_annotation.py` | `passive_display_only` | `tests/test_passive_node_contracts.py` |
| `passive.annotation.section_header` | Section Header | `passive` | `TrustedFactoryEntry` | `ea_node_editor/nodes/builtins/passive_annotation.py` | `passive_display_only` | `tests/test_passive_node_contracts.py` |
| `passive.annotation.sticky_note` | Sticky Note | `passive` | `TrustedFactoryEntry` | `ea_node_editor/nodes/builtins/passive_annotation.py` | `passive_display_only` | `tests/test_passive_node_contracts.py` |
| `passive.annotation.text` | Text | `passive` | `TrustedFactoryEntry` | `ea_node_editor/nodes/builtins/passive_annotation.py` | `passive_display_only` | `tests/test_passive_node_contracts.py` |
| `passive.flowchart.actor` | Actor | `passive` | `TrustedFactoryEntry` | `ea_node_editor/nodes/builtins/passive_flowchart.py` | `passive_display_only` | `tests/test_passive_node_contracts.py` |
| `passive.flowchart.callout` | Callout | `passive` | `TrustedFactoryEntry` | `ea_node_editor/nodes/builtins/passive_flowchart.py` | `passive_display_only` | `tests/test_passive_node_contracts.py` |
| `passive.flowchart.card` | Card | `passive` | `TrustedFactoryEntry` | `ea_node_editor/nodes/builtins/passive_flowchart.py` | `passive_display_only` | `tests/test_passive_node_contracts.py` |
| `passive.flowchart.connector` | Connector | `passive` | `TrustedFactoryEntry` | `ea_node_editor/nodes/builtins/passive_flowchart.py` | `passive_display_only` | `tests/test_passive_node_contracts.py` |
| `passive.flowchart.cube` | Cube | `passive` | `TrustedFactoryEntry` | `ea_node_editor/nodes/builtins/passive_flowchart.py` | `passive_display_only` | `tests/test_passive_node_contracts.py` |
| `passive.flowchart.database` | Database | `passive` | `TrustedFactoryEntry` | `ea_node_editor/nodes/builtins/passive_flowchart.py` | `passive_display_only` | `tests/test_passive_node_contracts.py` |
| `passive.flowchart.decision` | Decision | `passive` | `TrustedFactoryEntry` | `ea_node_editor/nodes/builtins/passive_flowchart.py` | `passive_display_only` | `tests/test_passive_node_contracts.py` |
| `passive.flowchart.document` | Document | `passive` | `TrustedFactoryEntry` | `ea_node_editor/nodes/builtins/passive_flowchart.py` | `passive_display_only` | `tests/test_passive_node_contracts.py` |
| `passive.flowchart.end` | End | `passive` | `TrustedFactoryEntry` | `ea_node_editor/nodes/builtins/passive_flowchart.py` | `passive_display_only` | `tests/test_passive_node_contracts.py` |
| `passive.flowchart.input_output` | Input / Output | `passive` | `TrustedFactoryEntry` | `ea_node_editor/nodes/builtins/passive_flowchart.py` | `passive_display_only` | `tests/test_passive_node_contracts.py` |
| `passive.flowchart.isometric_cube` | Isometric Cube | `passive` | `TrustedFactoryEntry` | `ea_node_editor/nodes/builtins/passive_flowchart.py` | `passive_display_only` | `tests/test_passive_node_contracts.py` |
| `passive.flowchart.message` | Message | `passive` | `TrustedFactoryEntry` | `ea_node_editor/nodes/builtins/passive_flowchart.py` | `passive_display_only` | `tests/test_passive_node_contracts.py` |
| `passive.flowchart.multi_document` | Multi-Document | `passive` | `TrustedFactoryEntry` | `ea_node_editor/nodes/builtins/passive_flowchart.py` | `passive_display_only` | `tests/test_passive_node_contracts.py` |
| `passive.flowchart.predefined_process` | Predefined Process | `passive` | `TrustedFactoryEntry` | `ea_node_editor/nodes/builtins/passive_flowchart.py` | `passive_display_only` | `tests/test_passive_node_contracts.py` |
| `passive.flowchart.process` | Process | `passive` | `TrustedFactoryEntry` | `ea_node_editor/nodes/builtins/passive_flowchart.py` | `passive_display_only` | `tests/test_passive_node_contracts.py` |
| `passive.flowchart.star` | Star | `passive` | `TrustedFactoryEntry` | `ea_node_editor/nodes/builtins/passive_flowchart.py` | `passive_display_only` | `tests/test_passive_node_contracts.py` |
| `passive.flowchart.start` | Start | `passive` | `TrustedFactoryEntry` | `ea_node_editor/nodes/builtins/passive_flowchart.py` | `passive_display_only` | `tests/test_passive_node_contracts.py` |
| `passive.flowchart.tick` | Tick | `passive` | `TrustedFactoryEntry` | `ea_node_editor/nodes/builtins/passive_flowchart.py` | `passive_display_only` | `tests/test_passive_node_contracts.py` |
| `passive.flowchart.timestamp` | Timestamp | `passive` | `TrustedFactoryEntry` | `ea_node_editor/nodes/builtins/passive_flowchart.py` | `passive_display_only` | `tests/test_passive_node_contracts.py` |
| `passive.flowchart.x` | X | `passive` | `TrustedFactoryEntry` | `ea_node_editor/nodes/builtins/passive_flowchart.py` | `passive_display_only` | `tests/test_passive_node_contracts.py` |
| `passive.media.mail_panel` | Mail Panel | `passive` | `TrustedFactoryEntry` | `ea_node_editor/nodes/builtins/passive_mail.py` | `passive_display_only` | `tests/test_passive_node_contracts.py` |
| `passive.planning.decision_card` | Decision Card | `passive` | `TrustedFactoryEntry` | `ea_node_editor/nodes/builtins/passive_planning.py` | `passive_display_only` | `tests/test_passive_node_contracts.py` |
| `passive.planning.milestone_card` | Milestone Card | `passive` | `TrustedFactoryEntry` | `ea_node_editor/nodes/builtins/passive_planning.py` | `passive_display_only` | `tests/test_passive_node_contracts.py` |
| `passive.planning.risk_card` | Risk Card | `passive` | `TrustedFactoryEntry` | `ea_node_editor/nodes/builtins/passive_planning.py` | `passive_display_only` | `tests/test_passive_node_contracts.py` |
| `passive.planning.task_card` | Task Card | `passive` | `TrustedFactoryEntry` | `ea_node_editor/nodes/builtins/passive_planning.py` | `passive_display_only` | `tests/test_passive_node_contracts.py` |
| `web.page_viewer` | Web Page Viewer | `passive` | `TrustedFactoryEntry` | `ea_node_editor/nodes/builtins/web_viewer.py` | `passive_display_only` | `tests/test_web_page_viewer_node.py` |

## Runtime Eligibility Notes

- The table scope is the maximum metadata value. Preparation must still reject
  unsupported values, sensitive properties, stale handles, changed files,
  incomplete artifact integrity, missing environment facts, and unavailable
  codecs with a deterministic reason code.
- `durable` rows become session-only when an accepted concrete output is not
  portable, exceeds bounded inline limits, or resolves to a live/runtime-local
  carrier.
- `session` rows never publish durable records unless a later accepted
  classification revision supplies complete portable provenance and codecs.
- Public declarations remain outside the 147-row repo-owned total and cannot
  increase any total in this document.

## Validation Contract

Review and implementation checks must prove all of the following:

1. The executable table has exactly 109 unique repo-owned type IDs and the excluded
   table has exactly 38 unique IDs with no overlap.
2. Executable totals are exactly 29 `durable`, 27 `session`, and 53 `never`.
3. The excluded table contains exactly 35 passive and 3 compile-only rows.
4. Every executable row contains all fourteen required columns and every excluded
   row contains all seven required columns.
5. `engineering.cad_import` and `model.viewer` are `session` with the exact
   content/importer and live-handle/transport reasons stated above.
6. Runtime-discovered public declarations are hard-locked to `never` without
   recording private IDs or paths.
7. `tests/fixtures/node_catalog/current_repo_owned_catalog.json` contains exactly
   the 147 classified rows.

This draft intentionally contains no implementation or acceptance claim. Metadata
edits remain forbidden until independent classification review closes all findings
and the orchestrator freezes this file's SHA-256 in the task ledger.
