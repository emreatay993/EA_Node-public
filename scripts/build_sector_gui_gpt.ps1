[CmdletBinding()]
param(
    [switch]$Clean,
    [switch]$DryRun,
    [switch]$Console,
    [string]$PythonExe = "",
    [string]$AppName = "Sector_GUI_GPT",
    [string]$DistRoot = "",
    [string]$WorkRoot = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$sourceScript = Join-Path $repoRoot "scripts\Sector_gui_gpt.py"
$defaultArtifactRoot = Join-Path $repoRoot "artifacts\pyinstaller\sector_gui_gpt"

if ([string]::IsNullOrWhiteSpace($PythonExe)) {
    $PythonExe = Join-Path $repoRoot "venv\Scripts\python.exe"
}
if ([string]::IsNullOrWhiteSpace($DistRoot)) {
    $DistRoot = Join-Path $defaultArtifactRoot "dist"
}
if ([string]::IsNullOrWhiteSpace($WorkRoot)) {
    $WorkRoot = Join-Path $defaultArtifactRoot "build"
}

$PythonExe = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($PythonExe)
$DistRoot = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($DistRoot)
$WorkRoot = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($WorkRoot)
$appFolder = Join-Path $DistRoot $AppName
$exePath = Join-Path $appFolder "$AppName.exe"
$internalFolder = Join-Path $appFolder "_internal"

function Assert-PathUnderRoot {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$Root,
        [Parameter(Mandatory = $true)]
        [string]$Label
    )

    $resolvedRoot = [System.IO.Path]::GetFullPath($Root).TrimEnd('\', '/')
    $resolvedPath = [System.IO.Path]::GetFullPath($Path).TrimEnd('\', '/')
    if (-not ($resolvedPath.Equals($resolvedRoot, [System.StringComparison]::OrdinalIgnoreCase) -or
            $resolvedPath.StartsWith($resolvedRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase))) {
        throw "$Label path is outside the expected root. Path='$resolvedPath', root='$resolvedRoot'."
    }
}

function Test-PythonModule {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ModuleName
    )

    $probe = "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('$ModuleName') else 1)"
    & $PythonExe -c $probe | Out-Null
    return $LASTEXITCODE -eq 0
}

function Assert-BuildEnvironment {
    if (-not (Test-Path $PythonExe)) {
        throw "Python executable was not found: $PythonExe"
    }
    if (-not (Test-Path $sourceScript)) {
        throw "GUI source script was not found: $sourceScript"
    }

    $missing = @()
    foreach ($module in @(
            "PyInstaller",
            "PyQt6",
            "pyvista",
            "pyvistaqt",
            "vtkmodules",
            "pandas",
            "numpy",
            "qtpy"
        )) {
        if (-not (Test-PythonModule -ModuleName $module)) {
            $missing += $module
        }
    }
    if ($missing.Count -gt 0) {
        throw (
            "The build environment is missing required modules: $($missing -join ', '). " +
            "Install the script dependencies first, for example: " +
            ".\venv\Scripts\python.exe -m pip install pyinstaller pyqt6 pyvista pyvistaqt pandas numpy"
        )
    }

    $versionText = (& $PythonExe -m PyInstaller --version).Trim()
    $version = [version]$versionText
    if ($version.Major -lt 6) {
        throw "PyInstaller 6 or newer is required for the exposed _internal contents directory. Found: $versionText"
    }
}

Assert-BuildEnvironment
Assert-PathUnderRoot -Path $DistRoot -Root $defaultArtifactRoot -Label "DistRoot"
Assert-PathUnderRoot -Path $WorkRoot -Root $defaultArtifactRoot -Label "WorkRoot"

$buildArgs = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--onedir",
    "--windowed",
    "--name", $AppName,
    "--contents-directory", "_internal",
    "--workpath", $WorkRoot,
    "--distpath", $DistRoot,
    "--specpath", $WorkRoot,
    "--paths", $repoRoot,
    "--collect-all", "pyvista",
    "--collect-all", "pyvistaqt",
    "--collect-all", "vtkmodules",
    "--copy-metadata", "pyvista",
    "--copy-metadata", "pyvistaqt",
    "--copy-metadata", "vtk",
    "--hidden-import", "PyQt6.QtCore",
    "--hidden-import", "PyQt6.QtGui",
    "--hidden-import", "PyQt6.QtWidgets",
    "--hidden-import", "PyQt6.QtOpenGLWidgets",
    "--hidden-import", "numpy",
    "--hidden-import", "pandas",
    "--hidden-import", "qtpy",
    "--exclude-module", "PyQt5",
    "--exclude-module", "PySide2",
    "--exclude-module", "PySide6",
    $sourceScript
)

if ($Console) {
    $windowedIndex = [Array]::IndexOf($buildArgs, "--windowed")
    if ($windowedIndex -ge 0) {
        $buildArgs[$windowedIndex] = "--console"
    }
}

Write-Host "Source: $sourceScript"
Write-Host "Executable: $exePath"
Write-Host "Internal folder: $internalFolder"
Write-Host "PyInstaller contents directory: _internal"

if ($DryRun) {
    Write-Host "Dry run only. Command:"
    Write-Host "& `"$PythonExe`" $($buildArgs -join ' ')"
    exit 0
}

if ($Clean) {
    foreach ($path in @($DistRoot, $WorkRoot)) {
        Assert-PathUnderRoot -Path $path -Root $defaultArtifactRoot -Label "Clean target"
        if (Test-Path $path) {
            Remove-Item -Recurse -Force $path
        }
    }
}

New-Item -ItemType Directory -Path $DistRoot -Force | Out-Null
New-Item -ItemType Directory -Path $WorkRoot -Force | Out-Null

& $PythonExe @buildArgs
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed with exit code $LASTEXITCODE."
}

if (-not (Test-Path $exePath)) {
    throw "Expected executable was not created: $exePath"
}
if (-not (Test-Path $internalFolder)) {
    throw "Expected exposed _internal folder was not created: $internalFolder"
}

Write-Host "Build complete: $exePath"
Write-Host "Keep $AppName.exe beside the exposed _internal folder when copying the app."
