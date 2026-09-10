# -*- mode: python ; coding: utf-8 -*-

from __future__ import annotations

import importlib.util
import os
from pathlib import Path, PurePosixPath

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata


_SPEC_PATH = Path(globals().get("__file__", Path.cwd() / "ea_node_editor.spec")).resolve()
PROJECT_ROOT = _SPEC_PATH.parent
PACKAGE_PROFILE_ENV_VAR = "EA_NODE_EDITOR_PACKAGE_PROFILE"
PACKAGE_APP_NAME = "COREX_Node_Editor"
BASE_PACKAGE_PROFILE = "base"
VIEWER_PACKAGE_PROFILE = "viewer"
WEB_PACKAGE_PROFILE = "web"
FULL_PACKAGE_PROFILE = "full"
PACKAGE_PROFILES = ("base", "viewer", "web", "full")
VIEWER_RUNTIME_HIDDENIMPORT_PACKAGES = (
    "OCP",
    "pyvista",
    "pyvistaqt",
    "qtpy",
    "vtkmodules",
)
VIEWER_RUNTIME_METADATA_DISTRIBUTIONS = (
    "cadquery-ocp-novtk",
    "cadquery-ocp-proxy",
    "pyvista",
    "pyvistaqt",
    "vtk",
)
TABULAR_RUNTIME_HIDDENIMPORT_MODULES = (
    "numpy",
    "pandas",
    "polars",
    "pyarrow",
    "pyarrow.compute",
    "pyarrow.csv",
    "pyarrow.dataset",
    "pyarrow.fs",
    "pyarrow.parquet",
    "duckdb",
    "openpyxl",
    "h5py",
    "tables",
)
TABULAR_RUNTIME_METADATA_DISTRIBUTIONS = (
    "numpy",
    "pandas",
    "polars",
    "pyarrow",
    "duckdb",
    "openpyxl",
    "h5py",
    "tables",
)
FULL_RUNTIME_REQUIRED_PACKAGES = (
    "OCP",
    "ansys.mechanical.core",
    "ansys.workbench.core",
    "duckdb",
    "h5py",
    "llvmlite",
    "matplotlib",
    "numba",
    "numpy",
    "openpyxl",
    "pandas",
    "polars",
    "pyarrow",
    "pyqtgraph",
    "pyvista",
    "pyvistaqt",
    "scipy",
    "tables",
    "vtkmodules",
)
FULL_RUNTIME_HIDDENIMPORT_PACKAGES = (
    "ansys.mechanical.core",
    "ansys.workbench.core",
    "matplotlib",
    "numba",
    "pyqtgraph",
    "scipy",
)
FULL_RUNTIME_METADATA_DISTRIBUTIONS = (
    "ansys-mechanical-core",
    "ansys-workbench-core",
    "llvmlite",
    "matplotlib",
    "numba",
    "pyqtgraph",
    "scipy",
)
QT_BINDING_EXCLUDES = (
    "PyQt5",
    "PySide2",
    "PySide6",
)
OPTIONAL_ML_VISION_EXCLUDES = (
    "accelerate",
    "cv2",
    "huggingface_hub",
    "onnxruntime",
    "safetensors",
    "tensorflow",
    "tokenizers",
    "torch",
    "torchvision",
    "transformers",
)
PYINSTALLER_EXCLUDES = (
    "PyQt5",
    "PySide2",
    "PySide6",
    "accelerate",
    "cv2",
    "huggingface_hub",
    "onnxruntime",
    "safetensors",
    "tensorflow",
    "tokenizers",
    "torch",
    "torchvision",
    "transformers",
    "ansys.dpf",
    "ansys.grpc.dpf",
)
NON_FULL_RUNTIME_EXCLUDES = ("ansys",)
NON_FULL_RUNTIME_DATA_EXCLUDE_PREFIXES = ("ansys_",)
DPF_RUNTIME_PAYLOAD_EXCLUDE_PREFIXES = (
    "ansys/dpf",
    "ansys/grpc/dpf",
    "ansys_dpf",
    "ansys-dpf",
)
# PyInstaller's Windows bindepend step imports every collected package inside a
# single isolated child process only to record DLL search-path changes (PATH
# edits and os.add_dll_directory calls). In that DLL-heavy child, numba's
# import-time LLVM JIT self-check (llvmlite check_jit_execution) deadlocks and
# pyarrow's arrow.dll static initializers can access-violate, hanging or
# killing full-profile builds. None of these packages register extra DLL
# search directories at import time -- their native libraries live inside the
# package directories and are collected through hooks -- so dropping them from
# that child's import list is collection-safe. PyInstaller upstream suppresses
# pyqtgraph.canvas and PySimpleGUI in the same child for the same reason.
BINDEPEND_IMPORT_SUPPRESSIONS = (
    "ea_node_editor",
    "llvmlite",
    "numba",
    "pyarrow",
)
VIEWER_SIBLING_BINARY_PATTERNS = {
    "OCP": {
        "cadquery_ocp_novtk.libs": ("*.dll",),
    },
    "vtkmodules": {
        "vtk.libs": ("*.dll",),
    },
}
VIEWER_DATA_FILE_PATTERNS = {
    "pyvistaqt": ("data/*.png",),
}
WEB_RUNTIME_HIDDENIMPORT_MODULES = (
    "PyQt6.QtWebEngineCore",
    "PyQt6.QtWebEngineQuick",
    "PyQt6.QtWebEngineWidgets",
    "PyQt6.QtWebChannel",
)
QT_MULTIMEDIA_RUNTIME_HIDDENIMPORT_MODULES = (
    "PyQt6.QtMultimedia",
)
IMAGEIO_FFMPEG_RUNTIME_MODULES = (
    "imageio_ffmpeg",
)
IMAGEIO_FFMPEG_METADATA_DISTRIBUTIONS = (
    "imageio-ffmpeg",
)
IMAGEIO_FFMPEG_DATA_INCLUDES = (
    "binaries/*",
)
WEB_ASSET_DATA_INCLUDES = (
    "web_assets/**/*.html",
    "web_assets/**/*.css",
    "web_assets/**/*.js",
    "web_assets/**/*.mjs",
    "web_assets/**/*.cjs",
    "web_assets/**/*.chunk.js",
    "web_assets/**/*.chunk.css",
    "web_assets/**/*.json",
    "web_assets/**/*.webmanifest",
    "web_assets/**/asset-manifest.*",
    "web_assets/**/*.wasm",
    "web_assets/**/*.svg",
    "web_assets/**/*.png",
    "web_assets/**/*.jpg",
    "web_assets/**/*.jpeg",
    "web_assets/**/*.gif",
    "web_assets/**/*.webp",
    "web_assets/**/*.ico",
    "web_assets/**/*.woff",
    "web_assets/**/*.woff2",
    "web_assets/**/*.ttf",
    "web_assets/**/*.otf",
    "web_assets/**/*.eot",
    "web_assets/excalidraw_host/*",
    "web_assets/excalidraw_host/**/*",
)


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ModuleNotFoundError, ValueError):
        return False


def _module_roots(name: str) -> list[Path]:
    spec = importlib.util.find_spec(name)
    if spec is None:
        return []
    if spec.submodule_search_locations:
        return [Path(location).resolve() for location in spec.submodule_search_locations]
    if spec.origin:
        return [Path(spec.origin).resolve().parent]
    return []


def _package_profile() -> str:
    profile = os.environ.get(PACKAGE_PROFILE_ENV_VAR, BASE_PACKAGE_PROFILE).strip().lower()
    if profile not in set(PACKAGE_PROFILES):
        raise RuntimeError(
            f"Unsupported {PACKAGE_PROFILE_ENV_VAR}={profile!r}. "
            f"Expected one of: {', '.join(repr(candidate) for candidate in PACKAGE_PROFILES)}."
        )
    return profile


def _target_dir(dest_root: str, source_root: Path, source_path: Path) -> str:
    relative_parent = source_path.parent.relative_to(source_root)
    target = PurePosixPath(dest_root)
    if str(relative_parent) not in {"", "."}:
        target /= PurePosixPath(relative_parent.as_posix())
    return target.as_posix()


def _collect_globbed_files(source_root: Path, dest_root: str, patterns: tuple[str, ...]) -> list[tuple[str, str]]:
    collected: list[tuple[str, str]] = []
    for pattern in patterns:
        for source_path in sorted(source_root.glob(pattern)):
            if not source_path.is_file():
                continue
            collected.append((str(source_path), _target_dir(dest_root, source_root, source_path)))
    return collected


def _collect_viewer_hiddenimports() -> list[str]:
    hidden_imports: list[str] = []
    for package_name in VIEWER_RUNTIME_HIDDENIMPORT_PACKAGES:
        if _module_available(package_name):
            hidden_imports += collect_submodules(package_name)
    return hidden_imports


def _collect_viewer_datas() -> list[tuple[str, str]]:
    data_files: list[tuple[str, str]] = []
    for package_name, patterns in VIEWER_DATA_FILE_PATTERNS.items():
        if _module_available(package_name):
            data_files += collect_data_files(package_name, includes=list(patterns))
    for distribution_name in VIEWER_RUNTIME_METADATA_DISTRIBUTIONS:
        data_files += copy_metadata(distribution_name)
    return data_files


def _collect_tabular_hiddenimports() -> list[str]:
    return [module_name for module_name in TABULAR_RUNTIME_HIDDENIMPORT_MODULES if _module_available(module_name)]


def _collect_tabular_datas() -> list[tuple[str, str]]:
    data_files: list[tuple[str, str]] = []
    for distribution_name in TABULAR_RUNTIME_METADATA_DISTRIBUTIONS:
        if not _module_available(distribution_name):
            continue
        try:
            data_files += copy_metadata(distribution_name)
        except Exception:
            continue
    return data_files


def _collect_full_hiddenimports() -> list[str]:
    return [package_name for package_name in FULL_RUNTIME_HIDDENIMPORT_PACKAGES if _module_available(package_name)]


def _collect_full_datas() -> list[tuple[str, str]]:
    data_files: list[tuple[str, str]] = []
    for distribution_name in FULL_RUNTIME_METADATA_DISTRIBUTIONS:
        data_files += copy_metadata(distribution_name)
    return data_files


def _collect_viewer_sibling_binaries() -> list[tuple[str, str]]:
    binaries: list[tuple[str, str]] = []
    for anchor_module, sibling_patterns in VIEWER_SIBLING_BINARY_PATTERNS.items():
        for anchor_root in _module_roots(anchor_module):
            site_packages_root = anchor_root.parent
            for sibling_dir, patterns in sibling_patterns.items():
                source_root = site_packages_root / sibling_dir
                if source_root.is_dir():
                    binaries += _collect_globbed_files(source_root, sibling_dir, patterns)
    return binaries


def _collect_web_hiddenimports(*, require: bool) -> list[str]:
    missing = [module_name for module_name in WEB_RUNTIME_HIDDENIMPORT_MODULES if not _module_available(module_name)]
    if missing and require:
        raise RuntimeError(
            "Packaging requires the PyQt6 WebEngine/WebChannel runtime stack "
            f"in the build environment. Missing modules: {', '.join(missing)}."
        )
    return [module_name for module_name in WEB_RUNTIME_HIDDENIMPORT_MODULES if module_name not in missing]


def _collect_qt_multimedia_hiddenimports(*, require: bool) -> list[str]:
    missing = [
        module_name for module_name in QT_MULTIMEDIA_RUNTIME_HIDDENIMPORT_MODULES if not _module_available(module_name)
    ]
    if missing and require:
        raise RuntimeError(
            "Packaging requires the PyQt6 Qt Multimedia runtime stack "
            f"in the build environment. Missing modules: {', '.join(missing)}."
        )
    return [module_name for module_name in QT_MULTIMEDIA_RUNTIME_HIDDENIMPORT_MODULES if module_name not in missing]


def _collect_imageio_ffmpeg_payload(*, require: bool) -> tuple[list[str], list[tuple[str, str]]]:
    missing = [module_name for module_name in IMAGEIO_FFMPEG_RUNTIME_MODULES if not _module_available(module_name)]
    if missing and require:
        raise RuntimeError(
            "Packaging requires imageio-ffmpeg for bundled Media Panel video trimming. "
            f"Missing modules: {', '.join(missing)}."
        )
    hidden = [module_name for module_name in IMAGEIO_FFMPEG_RUNTIME_MODULES if module_name not in missing]
    data_files: list[tuple[str, str]] = []
    if hidden:
        data_files += collect_data_files("imageio_ffmpeg", includes=list(IMAGEIO_FFMPEG_DATA_INCLUDES))
        for distribution_name in IMAGEIO_FFMPEG_METADATA_DISTRIBUTIONS:
            data_files += copy_metadata(distribution_name)
    return hidden, data_files


def _require_modules(label: str, package_names: tuple[str, ...]) -> None:
    missing = [package_name for package_name in package_names if not _module_available(package_name)]
    if missing:
        raise RuntimeError(
            f"{label} packaging profile requires its runtime stack in the build environment. "
            f"Missing modules: {', '.join(missing)}."
        )


def _require_viewer_stack() -> None:
    _require_modules("Viewer", ("OCP", "pyvista", "pyvistaqt", "vtkmodules"))


def _require_full_stack() -> None:
    _require_modules("Full", FULL_RUNTIME_REQUIRED_PACKAGES)


def _suppress_bindepend_native_imports() -> None:
    """Keep BINDEPEND_IMPORT_SUPPRESSIONS out of the bindepend child imports.

    PyInstaller 6.x exposes no public knob for the package list its Windows
    find_binary_dependencies child imports, so wrap the module-level function
    and filter the list before it runs.
    """

    from PyInstaller.building import build_main

    original = build_main.find_binary_dependencies
    if getattr(original, "_corex_bindepend_suppressions", None) == BINDEPEND_IMPORT_SUPPRESSIONS:
        return

    def find_binary_dependencies_without_native_crashers(binaries, import_packages, *args, **kwargs):
        safe_import_packages = [
            package_name
            for package_name in import_packages
            if not _matches_module_prefix(package_name, BINDEPEND_IMPORT_SUPPRESSIONS)
        ]
        return original(binaries, safe_import_packages, *args, **kwargs)

    find_binary_dependencies_without_native_crashers._corex_bindepend_suppressions = BINDEPEND_IMPORT_SUPPRESSIONS
    build_main.find_binary_dependencies = find_binary_dependencies_without_native_crashers


def _matches_module_prefix(module_name: str, prefixes) -> bool:
    return any(module_name == prefix or module_name.startswith(f"{prefix}.") for prefix in prefixes)


def _matches_data_target_prefix(target_name: str, prefixes) -> bool:
    normalized = str(target_name).replace("\\", "/").lower()
    return any(normalized.startswith(str(prefix).lower()) for prefix in prefixes)


package_profile = _package_profile()
_require_modules("Every", ("paramiko", "xy"))
full_profile_enabled = package_profile == FULL_PACKAGE_PROFILE
viewer_payload_enabled = package_profile in {VIEWER_PACKAGE_PROFILE, FULL_PACKAGE_PROFILE}
analysis_excludes = list(PYINSTALLER_EXCLUDES)
if not full_profile_enabled:
    analysis_excludes.extend(NON_FULL_RUNTIME_EXCLUDES)

hiddenimports = collect_submodules("ea_node_editor.nodes.builtins")
hiddenimports += collect_submodules("ea_node_editor.addons.mars")
hiddenimports += collect_submodules("ea_node_editor.addons.tabular_data")
hiddenimports += [
    "corex",
    "PyQt6.QtPdf",
    "PyQt6.QtQml",
    "PyQt6.QtQuick",
    "PyQt6.QtQuickControls2",
    "PyQt6.QtQuickWidgets",
    "PyQt6.QtSvg",
]

if _module_available("openpyxl"):
    hiddenimports += collect_submodules("openpyxl")

hiddenimports += collect_submodules("paramiko")
hiddenimports += ["xy.components"]

hiddenimports += _collect_tabular_hiddenimports()

hiddenimports += _collect_web_hiddenimports(require=True)
hiddenimports += _collect_qt_multimedia_hiddenimports(require=True)
imageio_ffmpeg_hiddenimports, imageio_ffmpeg_datas = _collect_imageio_ffmpeg_payload(require=True)
hiddenimports += imageio_ffmpeg_hiddenimports

datas = []
datas += copy_metadata("paramiko")
datas += copy_metadata("xy")
datas += collect_data_files("xy", includes=["_native_lib/*"])
datas += [
    (str(PROJECT_ROOT / "THIRD_PARTY_NOTICES.md"), "."),
    (str(PROJECT_ROOT / "licenses" / "PARAMIKO-LGPL-2.1.txt"), "licenses"),
    (str(PROJECT_ROOT / "licenses" / "XY-APACHE-2.0-NOTICE.txt"), "licenses"),
    (str(PROJECT_ROOT / "licenses" / "OCP-APACHE-2.0.txt"), "licenses"),
]
datas += collect_data_files(
    "ea_node_editor.ui_qml",
    includes=[
        "*.qml",
        "**/*.qml",
        "*.js",
        "**/*.js",
        "*.svg",
        "**/*.svg",
        "*.json",
        "**/*.json",
        "*.txt",
        "**/*.txt",
        "**/*.qsb",
    ],
)
datas += collect_data_files(
    "ea_node_editor.ui.tooltips",
    includes=["*.json"],
)
datas += collect_data_files(
    "ea_node_editor.ui.theme",
    includes=["icons/*.svg"],
)
datas += collect_data_files(
    "ea_node_editor",
    includes=list(WEB_ASSET_DATA_INCLUDES),
)
datas += collect_data_files(
    "ea_node_editor",
    includes=[
        "mockups/**/*.qml",
        "mockups/**/*.js",
    ],
)
datas += _collect_tabular_datas()
datas += imageio_ffmpeg_datas
core_runtime_data_includes = [
    "assets/app_icon/*.svg",
    "assets/app_icon/*.png",
    "assets/app_icon/*.ico",
    "assets/fonts/*.ttf",
    "assets/fonts/*.txt",
    "assets/node_title_icons/**/*.svg",
    "assets/node_title_icons/**/*.png",
    "assets/node_title_icons/**/*.jpg",
    "assets/node_title_icons/**/*.jpeg",
    "addons/mars/icons/mars_icon_64.png",
]
datas += collect_data_files(
    "ea_node_editor",
    includes=core_runtime_data_includes,
)
binaries = []

# The viewer/full payload is opt-in so base and web Windows packages stay lean.
if viewer_payload_enabled:
    if full_profile_enabled:
        _require_full_stack()
    else:
        _require_viewer_stack()
    hiddenimports += _collect_viewer_hiddenimports()
    datas += _collect_viewer_datas()
    for notice_path, destination in (
        (PROJECT_ROOT / "LICENSE", "."),
        (PROJECT_ROOT / "THIRD_PARTY_NOTICES.md", "."),
        (PROJECT_ROOT / "licenses", "licenses"),
    ):
        datas.append((str(notice_path), destination))
    binaries += _collect_viewer_sibling_binaries()

if full_profile_enabled:
    hiddenimports += _collect_full_hiddenimports()
    datas += _collect_full_datas()

hiddenimports = sorted(
    module_name
    for module_name in set(hiddenimports)
    if not _matches_module_prefix(module_name, analysis_excludes)
)
datas = list(dict.fromkeys(datas))
binaries = list(dict.fromkeys(binaries))

_suppress_bindepend_native_imports()

a = Analysis(
    [str(PROJECT_ROOT / "ea_node_editor" / "bootstrap.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[str(PROJECT_ROOT / "scripts" / "pyinstaller_hooks")],
    hooksconfig={},
    runtime_hooks=[],
    excludes=analysis_excludes,
    noarchive=False,
    optimize=0,
)
a.datas = [
    entry
    for entry in a.datas
    if not _matches_data_target_prefix(entry[0], DPF_RUNTIME_PAYLOAD_EXCLUDE_PREFIXES)
]
a.binaries = [
    entry
    for entry in a.binaries
    if not _matches_data_target_prefix(entry[0], DPF_RUNTIME_PAYLOAD_EXCLUDE_PREFIXES)
]
if not full_profile_enabled:
    # Some third-party hooks copy installed distribution metadata even when
    # the matching Python namespace is excluded from Analysis. Keep neutral
    # viewer/base packages free of the optional Ansys runtime metadata too.
    a.datas = [
        entry
        for entry in a.datas
        if not _matches_data_target_prefix(entry[0], NON_FULL_RUNTIME_DATA_EXCLUDE_PREFIXES)
    ]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=PACKAGE_APP_NAME,
    icon=str(PROJECT_ROOT / "ea_node_editor" / "assets" / "app_icon" / "corex_app.ico"),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=PACKAGE_APP_NAME,
)
