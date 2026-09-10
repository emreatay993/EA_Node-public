# COREX Excalidraw Web Host Layer QA Matrix

- Updated: `2026-05-02`
- Packet sets: `COREX_EXCALIDRAW_WEB_HOST_LAYER` (`P01` through `P07`) plus `COREX_EXCALIDRAW_REAL_EDITOR` (`P01` through `P06`)
- Scope: final retained proof for the COREX-owned Excalidraw board surface. The shipped board is now a real local/offline Excalidraw editor with managed image imports, artifact-backed previews, fullscreen lifecycle integration, package/static asset proof, and docs/traceability closeout.

## Locked Scope

- Qt WebEngine is required and in-process for normal desktop source/package sessions; startup must remain graceful only for unsupported/headless fallback environments.
- The accepted editor is built from repo-local Vite/React source under `web/excalidraw_host/` and committed generated assets under `ea_node_editor/web_assets/excalidraw_host/`; no CDN or network-hosted editor content is allowed.
- Web assets are local/offline packaged files only. There is no external browser launch, no remote rooms, no collaboration services, and no network-hosted editor content.
- `excalidraw.board` is a passive built-in node with `runtime_behavior="passive"`, `surface_family="web"`, and `surface_variant="excalidraw_board"`.
- Drawing JSON persists only in hidden node property `excalidraw_state`; imported image bytes are externalized through `excalidraw_state.files[*].artifact_ref`, optional exported preview references persist only through `excalidraw_preview_ref`, and binary/image data stays in the existing `ProjectArtifactStore`.
- `.cxproj` documents must not persist `data:image` or base64 image payloads for Excalidraw image imports or previews.
- The web host layer has no execution semantics: web rendering, WebChannel bridge state, managed image import, preview export, and fullscreen editing must not enter compiled/runtime execution graphs or execution-worker WebEngine behavior.
- The host layer is COREX-owned and does not register arbitrary third-party plugin web UIs. Any future third-party surface/toolchain descriptor support requires a separate contract.
- The earlier `COREX_EXCALIDRAW_WEB_HOST_LAYER` placeholder bundle was a historical host-layer milestone. The follow-up `COREX_EXCALIDRAW_REAL_EDITOR` packet set supersedes that placeholder with the real local/offline editor while retaining the original non-goals.

## Retained Automated Verification

### Historical Host-Layer Baseline

| Coverage Area | Packet | Primary Requirement Anchors | Command | Recorded Source |
|---|---|---|---|---|
| Core `PyQt6-WebEngine` runtime dependency, lazy WebEngine availability checks, package-resource asset resolver, and historical local placeholder host bundle | `COREX_EXCALIDRAW_WEB_HOST_LAYER P01` | `REQ-INT-014`, `REQ-QA-045` | `.\venv\Scripts\python.exe -m pytest tests/test_corex_web_host_assets.py --ignore=venv -q` | PASS in `docs/specs/work_packets/corex_excalidraw_web_host_layer/P01_webengine_dependency_and_asset_resolver_WRAPUP.md` (`109733f7a302deabca330baa10a3b6c75859a046`) |
| Python-side WebChannel bridge contract, JSON validation, payload limits, placeholder-era response shape compatibility, and QtWebEngine-module-free bridge import behavior | `COREX_EXCALIDRAW_WEB_HOST_LAYER P02` | `REQ-INT-014`, `REQ-QA-045` | `.\venv\Scripts\python.exe -m pytest tests/test_corex_web_surface_bridge.py --ignore=venv -q` | PASS in `docs/specs/work_packets/corex_excalidraw_web_host_layer/P02_web_surface_bridge_contract_WRAPUP.md` (`78a2374abc579f69a70dbe068c616b1d6db2046b`) |
| Passive `excalidraw.board` built-in node contract, hidden project properties, registry validation, serializer round trip, and execution omission proof | `COREX_EXCALIDRAW_WEB_HOST_LAYER P03` | `REQ-NODE-030`, `REQ-NODE-031`, `REQ-PERSIST-024` | `.\venv\Scripts\python.exe -m pytest tests/test_excalidraw_board_node.py tests/test_passive_runtime_wiring.py tests/test_serializer.py --ignore=venv -q` | PASS in `docs/specs/work_packets/corex_excalidraw_web_host_layer/P03_excalidraw_board_node_contract_WRAPUP.md` (`11369373e7f4d5a2865a71631448a5a92d4b39ea`) |
| Compact graph web-board surface routing, fallback metadata panel, disabled WebEngine body pointer input, and surface action/input-rect contract | `COREX_EXCALIDRAW_WEB_HOST_LAYER P04` | `REQ-UI-044`, `REQ-QA-045` | `$env:QT_QPA_PLATFORM='offscreen'; .\venv\Scripts\python.exe -m pytest tests/test_graph_surface_input_contract.py tests/test_passive_graph_surface_host.py -k "web_board or excalidraw or surface_loader" --ignore=venv -q` | PASS in `docs/specs/work_packets/corex_excalidraw_web_host_layer/P04_compact_graph_web_surface_WRAPUP.md` (`f77facd2e0a9642e55a8705ef05912aa6b12c944`) |
| Fullscreen `web_editor` payload, active `WebSurfaceBridge`, local host wrapper, WebEngine-unavailable fallback, close/cleanup behavior, and hidden-state save path | `COREX_EXCALIDRAW_WEB_HOST_LAYER P05` | `REQ-UI-044`, `REQ-PERSIST-024`, `REQ-INT-014` | `$env:QT_QPA_PLATFORM='offscreen'; .\venv\Scripts\python.exe -m pytest tests/test_content_fullscreen_bridge.py tests/test_corex_web_surface_bridge.py tests/test_graph_surface_input_controls.py tests/test_passive_graph_surface_host.py -k "web_editor or excalidraw or web_board" --ignore=venv -q` | PASS in `docs/specs/work_packets/corex_excalidraw_web_host_layer/P05_fullscreen_web_editor_WRAPUP.md` (`1e00c761857b4b22930e5b83943cbdd728ebbab7`) |
| Package-data globs, PyInstaller asset collection, required WebEngine/WebChannel hidden imports, web package profile metadata, and static packaging smoke coverage | `COREX_EXCALIDRAW_WEB_HOST_LAYER P06` | `REQ-INT-014`, `REQ-QA-045` | `.\venv\Scripts\python.exe -m pytest tests/test_packaging_configuration.py tests/test_traceability_checker.py tests/test_corex_web_host_assets.py --ignore=venv -q` | PASS in `docs/specs/work_packets/corex_excalidraw_web_host_layer/P06_frozen_packaging_and_smoke_checks_WRAPUP.md` (`0d5775d29230aef29c91ab7fb2d640c682fafedf`) |
| Historical integrated regression, docs/proof checks, traceability anchors, markdown hygiene, verification-manifest proof, and fast verification gate | `COREX_EXCALIDRAW_WEB_HOST_LAYER P07` | `REQ-QA-045`, `AC-REQ-QA-045-01` | `$env:QT_QPA_PLATFORM='offscreen'; .\venv\Scripts\python.exe -m pytest tests/test_corex_web_host_assets.py tests/test_corex_web_surface_bridge.py tests/test_excalidraw_board_node.py tests/test_content_fullscreen_bridge.py tests/test_graph_surface_input_controls.py tests/test_passive_graph_surface_host.py tests/test_packaging_configuration.py --ignore=venv -q` | PASS in `docs/specs/work_packets/corex_excalidraw_web_host_layer/P07_regression_closeout_WRAPUP.md` (`d35085d2fd66a7bacab2c4fcf5be5e43a938997b`) |

### Real Editor Follow-Up

| Coverage Area | Packet | Primary Requirement Anchors | Command | Recorded Source |
|---|---|---|---|---|
| Local Vite/React Excalidraw host source, generated static dist, local-only asset scan, `qrc:///qtwebchannel/qwebchannel.js` bridge bootstrap, initial state loading, debounced state save hooks, artifact hydration hooks, and preview export hooks | `COREX_EXCALIDRAW_REAL_EDITOR P01` | `REQ-INT-014`, `REQ-QA-045` | `.\venv\Scripts\python.exe -m pytest tests/test_corex_web_host_assets.py --ignore=venv -q` | PASS in `docs/specs/work_packets/corex_excalidraw_real_editor/P01_js_host_bundle_WRAPUP.md` (`186c7cdac24958d23e18aaf49d7c6458b0581bbc`) |
| Managed image import externalization, artifact hydration, callback-backed metadata persistence, PNG preview export, supported image MIME checks, unsupported payload rejection, and WebEngine-free bridge import behavior | `COREX_EXCALIDRAW_REAL_EDITOR P02` | `REQ-PERSIST-024`, `REQ-INT-014`, `REQ-QA-045` | `.\venv\Scripts\python.exe -m pytest tests/test_corex_web_surface_bridge.py --ignore=venv -q` | PASS in `docs/specs/work_packets/corex_excalidraw_real_editor/P02_artifact_backed_web_bridge_WRAPUP.md` (`0b795f01cbda87b052709e816c185884114419f1`) |
| Fullscreen close lifecycle, live project artifact callbacks, accepted scene-save persistence, close-time preview export into `excalidraw_preview_ref`, preview-export failure tolerance, and artifact-backed compact preview projection | `COREX_EXCALIDRAW_REAL_EDITOR P03` | `REQ-UI-044`, `REQ-PERSIST-024`, `REQ-INT-014` | `$env:QT_QPA_PLATFORM='offscreen'; .\venv\Scripts\python.exe -m pytest tests/test_content_fullscreen_bridge.py tests/test_corex_web_surface_bridge.py tests/test_passive_graph_surface_host.py -k "web_editor or excalidraw or web_board or preview" --ignore=venv -q` | PASS in `docs/specs/work_packets/corex_excalidraw_real_editor/P03_fullscreen_lifecycle_and_preview_WRAPUP.md` (`855be262aa61974b325efd0e05c2846cd4c4fdec`) |
| Nested Excalidraw artifact-ref collection/rewrite, staged image and preview promotion to managed refs, no inline `data:image` or base64 payloads in saved `.cxproj`, and Save As self-contained copy coverage | `COREX_EXCALIDRAW_REAL_EDITOR P04` | `REQ-PERSIST-024`, `REQ-QA-045` | `.\venv\Scripts\python.exe -m pytest tests/serializer/round_trip_cases.py tests/test_project_artifact_store.py tests/test_project_save_as_flow.py --ignore=venv -q` | PASS in `docs/specs/work_packets/corex_excalidraw_real_editor/P04_persistence_save_as_refs_WRAPUP.md` (`88f82d7f421ec01b32e5fe35c3d1dbd07c40c73e`) |
| Editable package-data and frozen-build inclusion for the generated real editor bundle, recursive asset coverage for JS/CSS/font files, local source build script guard, and WebEngine/WebChannel package-profile checks | `COREX_EXCALIDRAW_REAL_EDITOR P05` | `REQ-INT-014`, `REQ-QA-045` | `.\venv\Scripts\python.exe -m pytest tests/test_packaging_configuration.py tests/test_corex_web_host_assets.py --ignore=venv -q` | PASS in `docs/specs/work_packets/corex_excalidraw_real_editor/P05_packaging_and_static_asset_proof_WRAPUP.md` (`486f8cad07d125e8afc3204aa99effdbd796aea8`) |
| Public specs, QA matrix, traceability rows, markdown hygiene, and verification-manifest/test proof updated from historical placeholder language to real local/offline editor semantics | `COREX_EXCALIDRAW_REAL_EDITOR P06` | `REQ-QA-045`, `AC-REQ-QA-045-01` | See `Final Closeout Commands` | Recorded in `docs/specs/work_packets/corex_excalidraw_real_editor/P06_docs_traceability_closeout_WRAPUP.md` |

## Final Closeout Commands

| Command | Purpose |
|---|---|
| `.\venv\Scripts\python.exe -m pytest tests/test_traceability_checker.py tests/test_markdown_hygiene.py tests/test_run_verification.py tests/test_pytest_defaults.py --ignore=venv -q` | Packet-owned docs/test-harness regression for retained requirement anchors, matrix registration, traceability rows, markdown-hygiene coverage, and verification-manifest proof |
| `.\venv\Scripts\python.exe scripts/check_traceability.py` | Proof audit for refreshed requirements, traceability rows, spec index registration, and closeout evidence |
| `.\venv\Scripts\python.exe scripts/check_markdown_links.py` | Markdown-link audit for the QA matrix, packet evidence paths, and spec index registration |
| `.\venv\Scripts\python.exe scripts/check_traceability.py` | P06 review gate before handoff |

## 2026-05-02 Execution Results

| Command | Result | Notes |
|---|---|---|
| `.\venv\Scripts\python.exe -m pytest tests/test_traceability_checker.py tests/test_markdown_hygiene.py tests/test_run_verification.py tests/test_pytest_defaults.py --ignore=venv -q` | `PASS` | `130 passed, 13 subtests passed`; docs, traceability, markdown hygiene, run-verification, pytest-defaults, and Excalidraw real-editor proof checks passed. |
| `.\venv\Scripts\python.exe scripts/check_traceability.py` | `PASS` | Required proof audit returned `TRACEABILITY CHECK PASS`. |
| `.\venv\Scripts\python.exe scripts/check_markdown_links.py` | `PASS` | Markdown-link audit returned `MARKDOWN LINK CHECK PASS`. |
| `.\venv\Scripts\python.exe scripts/check_traceability.py` | `PASS` | P06 review gate repeated the traceability audit before handoff. |

## Manual Test Directives

Ready for manual testing

Run these smoke checks after the P06 closeout branch is merged into the target checkout with the real-editor packet set.

1. Prerequisite: install or refresh the project environment from the repo venv, then launch from a normal desktop Qt session with `.\venv\Scripts\python.exe -m ea_node_editor.bootstrap`.
2. Local/offline asset smoke: run `Select-String -Path .\ea_node_editor\web_assets\excalidraw_host\* -Pattern 'https?://' -CaseSensitive:$false -List`. Expected result: the command prints no matches.
3. Fullscreen editor smoke: add an `Excalidraw Board`, open fullscreen, draw a simple shape, close through the close button, then reopen the board. Expected result: the real Excalidraw editor loads from local packaged assets, the scene reloads, and close succeeds without launching an external browser.
4. Managed image smoke: import a small PNG or JPEG through the Excalidraw editor, save the project, and inspect the saved `.cxproj`. Expected result: board state uses `artifact_ref` entries and no `data:image` or base64 image payload appears in the project JSON.
5. Preview smoke: after closing fullscreen, check the compact graph board surface. Expected result: a preview-backed board projection appears when preview export succeeds, and unsupported/headless WebEngine environments keep the explicit unavailable-authoring or last-preview fallback instead of failing the graph.
6. Save As smoke: Save As a self-contained copy of a project with an imported board image and preview. Expected result: referenced Excalidraw artifacts are present in the destination `.data` sidecar, stale staged scratch data is not copied, and refs still resolve after reopen.
7. Execution smoke: run an ordinary executable graph in the same workspace with an `excalidraw.board` present. Expected result: the board never participates in runtime execution snapshots and no worker-side WebEngine, WebChannel, preview export, or fullscreen editor behavior starts.

## Residual Risks

- Native WebEngine rendering and full PyInstaller/installer execution remain environment-dependent and should be validated in a Windows desktop packaging environment with project requirements installed.
- The pinned JavaScript dependency graph may continue to report npm peer/audit warnings and Vite bundle-size warnings; those are retained from the accepted local Excalidraw bundle proof.
- Unsupported WebEngine environments intentionally preserve unavailable-authoring or last-known-preview fallback behavior rather than guaranteeing live editor rendering.
- Collaboration, remote rooms, external-browser launch, execution-worker web behavior, and arbitrary third-party plugin web UI registration remain explicit non-goals.

## Packet Evidence Links

- `docs/specs/work_packets/corex_excalidraw_web_host_layer/COREX_EXCALIDRAW_WEB_HOST_LAYER_MANIFEST.md`
- `docs/specs/work_packets/corex_excalidraw_web_host_layer/COREX_EXCALIDRAW_WEB_HOST_LAYER_STATUS.md`
- `docs/specs/work_packets/corex_excalidraw_web_host_layer/P01_webengine_dependency_and_asset_resolver_WRAPUP.md`
- `docs/specs/work_packets/corex_excalidraw_web_host_layer/P02_web_surface_bridge_contract_WRAPUP.md`
- `docs/specs/work_packets/corex_excalidraw_web_host_layer/P03_excalidraw_board_node_contract_WRAPUP.md`
- `docs/specs/work_packets/corex_excalidraw_web_host_layer/P04_compact_graph_web_surface_WRAPUP.md`
- `docs/specs/work_packets/corex_excalidraw_web_host_layer/P05_fullscreen_web_editor_WRAPUP.md`
- `docs/specs/work_packets/corex_excalidraw_web_host_layer/P06_frozen_packaging_and_smoke_checks_WRAPUP.md`
- `docs/specs/work_packets/corex_excalidraw_web_host_layer/P07_regression_closeout_WRAPUP.md`
- `docs/specs/work_packets/corex_excalidraw_real_editor/COREX_EXCALIDRAW_REAL_EDITOR_MANIFEST.md`
- `docs/specs/work_packets/corex_excalidraw_real_editor/COREX_EXCALIDRAW_REAL_EDITOR_STATUS.md`
- `docs/specs/work_packets/corex_excalidraw_real_editor/P01_js_host_bundle_WRAPUP.md`
- `docs/specs/work_packets/corex_excalidraw_real_editor/P02_artifact_backed_web_bridge_WRAPUP.md`
- `docs/specs/work_packets/corex_excalidraw_real_editor/P03_fullscreen_lifecycle_and_preview_WRAPUP.md`
- `docs/specs/work_packets/corex_excalidraw_real_editor/P04_persistence_save_as_refs_WRAPUP.md`
- `docs/specs/work_packets/corex_excalidraw_real_editor/P05_packaging_and_static_asset_proof_WRAPUP.md`
- `docs/specs/work_packets/corex_excalidraw_real_editor/P06_docs_traceability_closeout_WRAPUP.md`
