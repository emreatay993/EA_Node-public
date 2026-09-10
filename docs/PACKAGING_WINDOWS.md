# Windows Packaging Guide

This repository ships Windows release artifacts from the repository-root
PyInstaller spec file `ea_node_editor.spec`. The active release flow is
profile-aware: `base` is the default packaged app, and `viewer` adds the
neutral CAD/FE viewer stack (`cadquery-ocp-novtk`, PyVista, PyVistaQt, and
VTK). The `full` profile is the developer-style all-feature application
package profile: it requires and freezes the current application runtime
stack, including PyMechanical, but explicitly excludes Ansys DPF. The Tabular
Data add-on is part of the base app surface but remains dependency-gated unless the
packaging venv includes the optional `tabular` stack.

## Prerequisites

- Use the project venv at `venv\`.
- Keep the MARS repository at the default sibling path `..\MARS_`, or pass an
  existing local wheel with `-MarsWheelPath`.
- Base profile: install `.[dev]` for the full developer/package stack, or at
  minimum `build` and `pyinstaller` in that venv for a minimal smokeable
  package with a managed-runtime wheel.
- Tabular-enabled base package: install `.[tabular]`, `.[all,dev]`, or `.[dev]`
  before packaging so `Data > Tabular Data Input` can register in the packaged
  app. Without those dependencies, the add-on remains dependency-gated.
- Viewer profile: install `.[viewer]` or `.[dev]` in that venv before
  packaging.
- Full profile: install `.[all,dev]` or `.[dev]` in that venv before packaging.
  This profile requires the PyMechanical, viewer/plot, tabular,
  Numba acceleration, Excel, web, and media runtime stacks and fails early
  when any import is missing.
- Web profile: use only when retaining isolated web-host packaging proof
  artifacts; normal release builds already include WebEngine/WebChannel and
  local web assets through the base profile.
- If the icon assets change, regenerate the committed SVG/PNG/ICO set first:
  `.\venv\Scripts\python.exe .\scripts\generate_app_icons.py`

## Build Commands

Base package with the default startup smoke check:

```powershell
.\scripts\build_windows_package.ps1 -PackageProfile base -Clean
```

Use this as the default Windows packaging command. A successful run builds the
`COREX_Node_Editor.exe` folder payload and then performs an offscreen startup
smoke check, a public function-plugin process-worker smoke that must return
`37`, and a native Signal Plot render smoke that must return a valid PNG. Each
check launches the packaged executable and must exit cleanly before the timeout,
so modal PyInstaller traceback dialogs, startup hangs, wrong function results,
invalid image bytes, and nonzero exits fail the build. Treat any smoke failure
as a broken packaged app, not as a successful build.

Neutral CAD/FE viewer package without the startup smoke check:

```powershell
.\scripts\build_windows_package.ps1 -PackageProfile viewer -Clean -SkipSmoke
```

Full developer-style package without the startup smoke check:

```powershell
.\scripts\build_windows_package.ps1 -PackageProfile full -Clean -SkipSmoke
```

Useful flags:

- `-SkipSmoke`: build only, no startup smoke check.
- `-SmokeSeconds <int>`: timeout for each packaged smoke check (default `30`).
- `-DependencyMatrixPath <path>`: override the generated dependency policy CSV.
  The default path is `artifacts\releases\packaging\<profile>\dependency_matrix.csv`.
- `-MarsSourcePath <path>`: local MARS source used to build the bundled wheel.
- `-MarsWheelPath <path>`: use an existing local MARS wheel instead of building
  the sibling repository. The build never downloads MARS from PyPI.

## Output Paths

- PyInstaller build cache: `artifacts\pyinstaller\build\<profile>\`
- PyInstaller dist root: `artifacts\pyinstaller\dist\<profile>\COREX_Node_Editor\`
- Base executable: `artifacts\pyinstaller\dist\base\COREX_Node_Editor\COREX_Node_Editor.exe`
- Viewer executable: `artifacts\pyinstaller\dist\viewer\COREX_Node_Editor\COREX_Node_Editor.exe`
- Full executable: `artifacts\pyinstaller\dist\full\COREX_Node_Editor\COREX_Node_Editor.exe`
- Managed runtime manifest: `artifacts\pyinstaller\dist\<profile>\COREX_Node_Editor\runtime\runtime_manifest.json`
- Managed runtime wheels: `artifacts\pyinstaller\dist\<profile>\COREX_Node_Editor\runtime\corex_node_editor-*.whl` and `mars_modal_response_solver-1.0.0-*.whl`
- Dependency matrix CSV: `artifacts\releases\packaging\<profile>\dependency_matrix.csv`

The build script sets `EA_NODE_EDITOR_PACKAGE_PROFILE` for the PyInstaller run,
verifies the expected executable exists, and by default runs three packaged
acceptance checks: offscreen startup with `EA_PROFILE_AUTOQUIT=1`, isolated
public function execution with the expected result `37`, and native Signal
Plot rendering with valid PNG bytes. It also builds a COREX runtime wheel, writes
`runtime\runtime_manifest.json` schema v2 with keyed `corex` and `mars`
packages. It copies both wheels into the packaged app so Workflow Settings or
the MARS Add-On Manager action can prepare the managed runtime later.

There is no separate tabular package profile. Tabular availability is decided by
the installed Python modules in the packaging venv: `numpy`, `pandas`, `polars`,
`pyarrow`, `duckdb`, `openpyxl`, `h5py`, and `tables`. The full profile also
requires the `numba` acceleration extra and its `llvmlite` runtime companion.
Package builds require Python 3.11 or newer and use `tables>=3.11` from
`pyproject.toml`. The `full` profile
makes this whole tabular and acceleration stack strict instead of
dependency-gated.

Every COREX app package profile excludes `ansys.dpf` and `ansys.grpc.dpf`,
including their binaries and metadata, even when PyDPF is installed in the
packaging environment. `ansys-dpf-core` remains in the `ansys`, `all`, and
`dev` extras only for standalone engineering utilities under `scripts/`; use
their dedicated build paths when packaging those tools. The full app profile
continues to include PyMechanical.

The viewer payload also carries `LICENSE`, `THIRD_PARTY_NOTICES.md`, and the
complete OCP/OCCT/VTK/PyVista license texts under `licenses\`. OCP's sibling
`cadquery_ocp_novtk.libs` directory is collected intact; it contains the
dynamically loaded OCCT libraries and must stay beside the packaged OCP module.
The notice records the matching OCP 7.9.3.1.1 and OCCT 7.9.3 source/build links.
Review the final dependency matrix and binary inventory before every commercial
release because transitive libraries can change independently of COREX source.

The PyInstaller output is a folder payload, not a single self-contained `.exe`.
Keep `COREX_Node_Editor.exe` next to its `_internal\` directory and launch it
from the generated `COREX_Node_Editor\` folder.

Full-profile builds use repo-local PyInstaller hook overrides from
`scripts\pyinstaller_hooks\` for dependency families where upstream hooks
collect broad test, benchmark, or optional native-adapter modules that COREX
does not use. Keep those hooks narrow and covered by
`tests/test_packaging_configuration.py` when adding packaged runtime modules.
The full profile also excludes unowned ML/vision stacks such as PyTorch,
Transformers, OpenCV, and ONNX Runtime when they are present in the packaging
venv only as transitive tooling dependencies.

The spec additionally keeps `numba`, `llvmlite`, and `pyarrow` out of the
import list of PyInstaller's Windows bindepend child process (the isolated
subprocess that imports every collected package to record DLL search-path
changes). Importing numba there hangs the build forever in llvmlite's
import-time JIT self-check, and importing pyarrow there can crash the child
inside `arrow.dll`; neither package registers DLL search directories at
import, so the suppression does not change what gets collected. A build that
sits silently after `INFO: Looking for dynamic libraries` is the signature of
this child hanging on a package import.

Open the packaged app directly from the repo root with:

```powershell
& .\artifacts\pyinstaller\dist\base\COREX_Node_Editor\COREX_Node_Editor.exe
```

## Installer Pipeline

Generate and validate an installer bundle from an existing dist folder:

```powershell
.\scripts\build_windows_installer.ps1 -PackageProfile base
```

Viewer installer bundle from the viewer dist output:

```powershell
.\scripts\build_windows_installer.ps1 -PackageProfile viewer
```

Full installer bundle from the full dist output:

```powershell
.\scripts\build_windows_installer.ps1 -PackageProfile full
```

Installer outputs are written under `artifacts\releases\installer\<profile>\<run_id>\`
and include:

- `COREX_Node_Editor_installer_bundle_<run_id>.zip`
- `scripts\Install-COREX_Node_Editor.ps1`
- `scripts\Uninstall-COREX_Node_Editor.ps1`
- `installer_manifest.json`
- `installer_validation.json`

The installer script validates install, clean offscreen startup with autoquit,
and uninstall before reporting `PASS`.

To hand the app to another Windows user, distribute the generated installer
bundle zip, extract it, and run:

```powershell
.\scripts\Install-COREX_Node_Editor.ps1
```

That installs the packaged folder under
`%LOCALAPPDATA%\COREX_Node_Editor\COREX_Node_Editor\`. The installed app opens
from:

- `%LOCALAPPDATA%\COREX_Node_Editor\COREX_Node_Editor\COREX_Node_Editor.exe`

The installer preserves and validates the packaged `runtime\` folder. That
folder is used by `Workflow Settings > Environment > Prepare COREX Runtime` to
install COREX and by **Add-On Manager > MARS > Install** to install and verify
`MARSBatch.exe` in the same app-managed venv. Third-party dependencies for the
COREX `[all]` extra are resolved by pip from the user's network.

Remove an installed bundle with:

```powershell
.\scripts\Uninstall-COREX_Node_Editor.ps1
```

## Signing and Verification

Capture a verify-only signing snapshot for the latest installer run in the
selected profile:

```powershell
.\scripts\sign_release_artifacts.ps1 -PackageProfile base -VerifyOnly
```

Use the same command shape for full-profile signing snapshots:

```powershell
.\scripts\sign_release_artifacts.ps1 -PackageProfile full -VerifyOnly
```

Sign then verify the latest profile-specific package and installer artifacts:

```powershell
.\scripts\sign_release_artifacts.ps1 -PackageProfile base -CertThumbprint <thumbprint> -TimestampServer <url> -RequireSignedArtifacts
```

The signing script defaults to profile-aware paths:

- Base signing output root: `artifacts\releases\signing\base\`
- Viewer signing output root: `artifacts\releases\signing\viewer\`
- Full signing output root: `artifacts\releases\signing\full\`
- Packaged executable: `artifacts\pyinstaller\dist\<profile>\COREX_Node_Editor\COREX_Node_Editor.exe`
- Installer root: `artifacts\releases\installer\<profile>\`

Environment variable equivalents:

- `EA_SIGN_CERT_THUMBPRINT`
- `EA_SIGN_TIMESTAMP_URL`
- `EA_SIGN_REQUIRE_SIGNED`

Each signing run writes:

- `artifacts\releases\signing\<profile>\<run_id>\signing_manifest.json`
- `artifacts\releases\signing\<profile>\<run_id>\signing_summary.md`

## Release-Doc Guardrails

- `tests/test_packaging_configuration.py` checks that `pyproject.toml`,
  `ea_node_editor.spec`, and the Windows packaging scripts stay aligned.
- `tests/test_markdown_hygiene.py` plus
  `.\venv\Scripts\python.exe .\scripts\check_markdown_links.py` catch broken
  canonical-doc links.
- `.\venv\Scripts\python.exe .\scripts\check_traceability.py` is the semantic
  proof gate for packaging, spec-index, pilot, and final QA-matrix drift.

See `docs/specs/perf/COREX_CLEAN_ARCHITECTURE_RESTRUCTURE_QA_MATRIX.md` for
the current clean-architecture closeout evidence, and
`docs/specs/perf/ARCHITECTURE_REFACTOR_QA_MATRIX.md` for older archived release
boundaries.
