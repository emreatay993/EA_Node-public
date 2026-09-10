# Hybrid Direct Tabular Auto-Plotting QA Matrix

- Date: `2026-05-23`
- Implementation commit: `108a721a7c16b6d7e850b8dd81a761a0f9fcefac`
- Scope: direct `TabularDataRef` / `ArrayDataRef` inputs for generic `plot.*` nodes, durable tabular selected-column hints, array-slice reuse, tabular ref reopen metadata, structured plot-side mapping controls, tabular auto-preview `plot_surface` payload fields such as `auto_preview*` and `render_request`, and unchanged backend-neutral render/export series contracts.

## Accepted Behavior

| Area | Proof |
| --- | --- |
| Tabular input persistence | `tabular.input` stores `tabular_selected_columns` as a list-valued node property; inline and fullscreen tabular surfaces persist header-selected columns through existing node property mutation paths. |
| Ref reopen metadata | Emitted tabular/array refs carry source URI, selected object, load options, selected columns, and slice metadata so downstream nodes can reopen sources without materializing whole tables in the graph document. |
| Plot normalization | Generic `plot.*` execution preserves existing dict/list/array behavior and only branches for `TabularDataRef` / `ArrayDataRef`; ref materialization follows `tabular_mapping` > selected columns/slice > schema/sample inference. |
| Backend contract | Matplotlib and pyqtgraph continue to receive existing `x`, `y`, `values`, and point/grid payloads; no backend-specific tabular API or Plotly/resampler dependency is introduced. |
| Runtime snapshot parity | Runtime snapshots omit deprecated plot-session layout state, matching serializer output while legacy `.cxproj` loads strip old `plot_session_layout` keys. |

## Verification

| Command | Result |
| --- | --- |
| `.\venv\Scripts\python.exe -m pytest tests/test_tabular_input_node.py tests/test_tabular_loaders.py tests/test_plot_node_contracts.py tests/test_content_fullscreen_bridge.py --ignore=venv -q` | PASS: `73 passed, 32 warnings` |
| `.\venv\Scripts\python.exe -m pytest tests/test_tabular_input_node.py tests/test_tabular_runtime_refs.py tests/test_plot_node_contracts.py tests/test_plot_headless_export.py --ignore=venv -q` | PASS: `34 passed, 32 warnings` |
| `.\venv\Scripts\python.exe -m pytest tests/test_plot_backend_pyqtgraph.py tests/test_passive_runtime_wiring.py --ignore=venv -q` | PASS: `15 passed, 24 warnings` |
| `.\venv\Scripts\python.exe -m pytest tests/test_registry_validation.py --ignore=venv -q` | PASS: `48 passed, 28 warnings, 5 subtests passed` |
| `.\venv\Scripts\python.exe .\scripts\check_traceability.py` | PASS |
| `.\venv\Scripts\python.exe .\scripts\check_markdown_links.py` | PASS |
| `git diff --check` | PASS, with Git CRLF working-copy notices only |

## Residual Risks

- Unknown row counts use a bounded fallback row limit and warning rather than backend downsampling.
- Streamlines require named `x/y/z/u/v/w` columns or explicit mapping.
- Header-click column selection is intentionally lightweight; richer multi-select affordances can be layered on the same persisted property later.
- Optional-package warnings outside the Tabular stack remain unrelated to this plotting path.
