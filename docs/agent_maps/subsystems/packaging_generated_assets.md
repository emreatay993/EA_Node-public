# Packaging And Generated Assets

## Purpose
Use this for package builds, installer builds, signing checks, generated architecture diagrams, app icons, web bundles, package metadata hygiene, and narrow static tooling configuration.

## Start Here
- `scripts/build_windows_package.ps1`
- `scripts/build_windows_installer.ps1`
- `scripts/sign_release_artifacts.ps1`
- `scripts/build_office_date_collector_gui.ps1`
- `scripts/build_sector_gui_gpt.ps1`
- `scripts/build_mcf_dpf_section_resultants_gui.ps1`
- `scripts/export_architecture_diagrams.py`
- `scripts/generate_app_icons.py`
- `scripts/build_canvas_grid_shader.ps1`
- `scripts/build_excalidraw_host.ps1`
- `ea_node_editor/ui/perf/`
- `pyproject.toml`
- `ea_node_editor.spec`
- `requirements.txt`
- `.gitignore`
- `docs/PLUGIN_AUTHORING_GUIDE.md`
- `docs/PLUGIN_MIGRATION_GUIDE.md`
- `docs/specs/perf/COREX_NOVICE_PLUGIN_SDK_QA_MATRIX.md`

## Do Not Start Here
- Generated output files when the source script should regenerate them.
- Tracked `*.egg-info/` metadata; treat it as generated output and keep it ignored.
- Broad packaging commands before focused docs/proof checks for docs-only changes.

## Common Changes
- Canvas grid shaders are baked with `scripts/build_canvas_grid_shader.ps1 -Qsb <Qt-bin/qsb.exe>` from `ea_node_editor/ui_qml/components/graph_canvas/shaders/grid.frag`. Commit the generated `grid.frag.qsb`; setuptools and PyInstaller must include it. The pack contains GLSL, HLSL, Metal and SPIR-V and requires no runtime shader compiler tool.
- Every package profile preflights exact Python 3.11 and `importlib.metadata.version("xy") == "0.0.6"` before PyInstaller, collects only XY's declarative `components` entrypoint, metadata, and `_native_lib/xy_core.dll`, and ships the Apache-2.0 notice. `-DependencyProbeOnly` executes this release gate without building. Do not collect all XY submodules because its optional pyplot/Reflex surfaces pull unrelated stacks into base packages. Packaged Signal Plot rendering is native and does not require Chromium or .NET.
- Regenerate generated architecture diagrams and icons from documented scripts.
- Every source/wheel/frozen build includes the top-level `corex` SDK. Default
  Windows package acceptance runs startup, a static-discovery-to-process-worker
  function-plugin smoke with exact result `37`, and Signal Plot rendering;
  `-SkipSmoke` is explicitly not acceptance evidence.
- The novice SDK QA matrix is the retained acceptance owner for the generated
  architecture exports, isolated wheel import, and default Windows package
  function-worker smoke. Do not record a `-SkipSmoke` build as closeout proof.
- Keep signing verification separate from packaging unless release work requires both.
- When optional dependency groups change, update `tests/test_packaging_configuration.py` with the exact expected dependency set.
- Keep static tooling baselines narrow and check-only unless a packet explicitly expands the gate.
- Keep generated packaging metadata such as `corex_node_editor.egg-info/` untracked and covered by `.gitignore`.
- Windows packages include a schema-v2 `runtime\runtime_manifest.json` plus contained COREX and MARS wheels; their app-managed venv installs COREX first and MARS with `--no-deps`. Source manifests point to editable local repositories, but add-on setup installs only MARS into the active COREX interpreter. Keep runtime preparation, package, and installer validation in sync.
- Keep add-on-owned runtime assets in both setuptools package data and PyInstaller data collection; the MARS node title icon is `addons/mars/icons/mars_icon_64.png`.
- Windows package profiles are `base`, `viewer`, `web`, and `full`. Use `full` for developer-style all-feature packages; it requires the all/dev runtime stack and should stay aligned across package, installer, signing, docs, and `tests/test_packaging_configuration.py`.
- The `viewer` profile is solver-neutral: it requires OCP/PyVista/PyVistaQt/VTK, excludes Ansys DPF, collects `cadquery_ocp_novtk.libs` beside `OCP`, and ships root/third-party notices plus complete OCP/OCCT/VTK/PyVista license texts. Every application package profile excludes DPF.
- PyInstaller tabular hidden imports are an explicit runtime-module list, not broad dependency submodule scans. Keep the list narrow so optional dependency test/dev paths such as Polars ML adapters do not pull unrelated ML/vision stacks into full packages.
- Full-profile packaging uses local hook overrides under `scripts/pyinstaller_hooks/` when upstream PyInstaller hooks collect optional native test/dev adapters that the app does not use; keep hook scope, spec `hookspath`, and packaging tests aligned.
- Full-profile Ansys packaging includes PyMechanical and PyWorkbench metadata/modules so the frozen private Mechanical owner role can open standalone and Workbench sources.
- The spec suppresses `numba`/`llvmlite`/`pyarrow` imports in PyInstaller's Windows bindepend child (`BINDEPEND_IMPORT_SUPPRESSIONS`): numba deadlocks in llvmlite's import-time JIT check and pyarrow can access-violate in `arrow.dll` there. A build stuck silently after `Looking for dynamic libraries` means that child is hanging on a package import; keep the suppression list, its spec wrapper, and `tests/test_packaging_configuration.py` aligned.
- Full-profile packages intentionally exclude unowned ML/vision stacks such as PyTorch, Transformers, OpenCV, and ONNX Runtime even when those packages exist in the packaging venv as transitive tooling dependencies.
- Full-profile packaging still supports the Numba acceleration stack; keep `numba`/`llvmlite` aligned across `pyproject.toml`, `ea_node_editor.spec`, `scripts/build_windows_package.ps1`, and `tests/test_packaging_configuration.py`.
- Media Panel video trim-save requires `imageio-ffmpeg` and its bundled ffmpeg executable in every package profile; keep `pyproject.toml`, `ea_node_editor.spec`, `scripts/build_windows_package.ps1`, and `tests/test_packaging_configuration.py` aligned.
- Canvas view PowerPoint export lazy-imports `python-pptx`; keep the `presentation` optional dependency group and its inclusion in `all`/`dev` aligned with `tests/test_packaging_configuration.py`.
- Paramiko is a required base dependency for the built-in SSH/SFTP nodes. Every Windows package profile collects its modules and metadata and ships `licenses/PARAMIKO-LGPL-2.1.txt`; do not reintroduce the retired `hpc` optional dependency group.
- The standalone Office Date Collector packages through `scripts/build_office_date_collector_gui.ps1` with PyInstaller `--onedir --windowed`, output under `artifacts/pyinstaller/office_date_collector/`, and a packaged `--self-test` smoke.
- The standalone Sector GUI GPT packages through `scripts/build_sector_gui_gpt.ps1` with PyInstaller `--onedir --windowed`, output under `artifacts/pyinstaller/sector_gui_gpt/`, and no packaged smoke because the upstream GUI has no self-test mode.
- The standalone MCF DPF Section Resultants GUI packages through `scripts/build_mcf_dpf_section_resultants_gui.ps1` from `scripts/mcf_dpf_section_resultants/gui.py` with PyInstaller `--onedir --windowed`, output under `artifacts/pyinstaller/mcf_dpf_section_resultants/`, explicit `ansys.dpf.gatebin` native-client DLL collection and post-build checks, and a packaged default-config smoke.

## Focused Verification
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_packaging_configuration.py --ignore=venv -q
.\venv\Scripts\python.exe .\scripts\export_architecture_diagrams.py
.\scripts\build_office_date_collector_gui.ps1 -DryRun
.\scripts\build_sector_gui_gpt.ps1 -DryRun
.\scripts\build_mcf_dpf_section_resultants_gui.ps1 -DryRun
```

## Breadcrumbs
- [Performance Harness And Graph Stress](../feature_routes/performance_harness_graph_stress.md)
- [Plotter Nodes](../feature_routes/plotter_nodes.md)
- [Retained Work-Packet QA Evidence And Spec Navigation](../feature_routes/work_packet_docs_status_qa.md)
- [MARS Solver Add-on](../feature_routes/mars_solver_addon.md)
- [SSH/SFTP Nodes](../feature_routes/ssh_sftp_nodes.md)

## Update Triggers
Update when build scripts, required or optional dependency groups, PyInstaller collection and hook overrides, third-party license payloads, static tooling baselines, generated asset scripts, signing policy, packaging tests, generated package metadata tracking, or generated output ownership changes.
