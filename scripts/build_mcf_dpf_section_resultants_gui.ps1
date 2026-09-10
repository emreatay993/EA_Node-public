[CmdletBinding()]
param(
    [switch]$Clean,
    [switch]$SkipSmoke,
    [switch]$DryRun,
    [switch]$Console,
    [string]$PythonExe = "",
    [string]$AppName = "MCF_DPF_Section_Resultants",
    [string]$DistRoot = "",
    [string]$WorkRoot = "",
    [ValidateRange(5, 120)]
    [int]$SmokeSeconds = 30
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$sourceScript = Join-Path $repoRoot "scripts\mcf_dpf_section_resultants\gui.py"
$hookPath = Join-Path $repoRoot "scripts\pyinstaller_hooks"
$defaultArtifactRoot = Join-Path $repoRoot "artifacts\pyinstaller\mcf_dpf_section_resultants"
$animationIconSourceFolder = Join-Path $repoRoot "scripts\mcf_dpf_section_resultants\assets\icons"
$animationIconBundleRelativePath = "mcf_dpf_section_resultants\icons"

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
$dpfGateBinFolder = Join-Path $internalFolder "ansys\dpf\gatebin"
$animationIconBundleFolder = Join-Path $internalFolder $animationIconBundleRelativePath
$requiredDpfClientDlls = @(
    "Ans.Dpf.GrpcClient.dll",
    "DPFClientAPI.dll"
)
$requiredAnimationIconFiles = @(
    "player-track-prev.svg",
    "player-play.svg",
    "player-pause.svg",
    "player-track-next.svg",
    "player-stop.svg",
    "loader-2.svg",
    "TABLER_SOURCES.txt",
    "TABLER_LICENSE.txt"
)

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
    if (-not (Test-Path $animationIconSourceFolder)) {
        throw "Animation icon source folder was not found: $animationIconSourceFolder"
    }
    foreach ($assetName in $requiredAnimationIconFiles) {
        $assetPath = Join-Path $animationIconSourceFolder $assetName
        if (-not (Test-Path $assetPath)) {
            throw "Required animation icon asset was not found: $assetPath"
        }
    }

    $missing = @()
    foreach ($module in @(
            "PyInstaller",
            "PyQt6",
            "PyQt6.QtSvg",
            "ansys.dpf.core",
            "ansys.dpf.gatebin",
            "pyvista",
            "pyvistaqt",
            "vtkmodules",
            "grpc",
            "matplotlib",
            "mplcursors",
            "numpy"
        )) {
        if (-not (Test-PythonModule -ModuleName $module)) {
            $missing += $module
        }
    }
    if ($missing.Count -gt 0) {
        throw (
            "The build environment is missing required modules: $($missing -join ', '). " +
            "Install the viewer/dev dependencies first, for example: " +
            ".\venv\Scripts\python.exe -m pip install -e `".[viewer,dev]`""
        )
    }

    $versionText = (& $PythonExe -m PyInstaller --version).Trim()
    $version = [version]$versionText
    if ($version.Major -lt 6) {
        throw "PyInstaller 6 or newer is required for the exposed _internal contents directory. Found: $versionText"
    }
}

function Invoke-ProcessChecked {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(Mandatory = $true)]
        [string[]]$ArgumentList,
        [string]$WorkingDirectory = $repoRoot,
        [string]$Label = "Process"
    )

    $process = Start-Process -FilePath $FilePath -ArgumentList $ArgumentList -WorkingDirectory $WorkingDirectory -PassThru -Wait -NoNewWindow
    if ($process.ExitCode -ne 0) {
        throw "$Label failed with exit code $($process.ExitCode)."
    }
}

function Invoke-PackagedSmoke {
    $tempConfigPath = Join-Path $env:TEMP ("mcf_dpf_section_resultants_default_" + [guid]::NewGuid().ToString("N") + ".json")
    $process = $null
    try {
        $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
        $startInfo.FileName = $exePath
        $startInfo.WorkingDirectory = $appFolder
        $startInfo.UseShellExecute = $false
        $startInfo.CreateNoWindow = $true
        $startInfo.Arguments = "--write-default-config `"$tempConfigPath`""
        $process = [System.Diagnostics.Process]::new()
        $process.StartInfo = $startInfo
        [void]$process.Start()
        if (-not $process.WaitForExit($SmokeSeconds * 1000)) {
            Stop-Process -Id $process.Id -Force
            $process.WaitForExit()
            throw "Packaged smoke failed: executable did not exit within $SmokeSeconds seconds."
        }
        if ($process.ExitCode -ne 0) {
            throw "Packaged smoke failed: executable exited with code $($process.ExitCode)."
        }
        if (-not (Test-Path $tempConfigPath)) {
            throw "Packaged smoke failed: default config was not written to $tempConfigPath."
        }
        Write-Host "Packaged smoke passed: default config command completed."
    }
    finally {
        if ($null -ne $process -and -not $process.HasExited) {
            Stop-Process -Id $process.Id -Force
        }
        Remove-Item -Path $tempConfigPath -Force -ErrorAction SilentlyContinue
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
    "--add-data", "$animationIconSourceFolder;$animationIconBundleRelativePath",
    "--additional-hooks-dir", $hookPath,
    "--collect-all", "ansys.dpf.core",
    "--collect-all", "ansys.dpf.gate",
    "--collect-all", "ansys.dpf.gatebin",
    "--collect-all", "ansys.grpc.dpf",
    "--collect-all", "pyvista",
    "--collect-all", "pyvistaqt",
    "--collect-all", "vtkmodules",
    "--collect-all", "matplotlib",
    "--collect-all", "mplcursors",
    "--copy-metadata", "ansys-dpf-core",
    "--copy-metadata", "pyvista",
    "--copy-metadata", "pyvistaqt",
    "--copy-metadata", "vtk",
    "--copy-metadata", "grpcio",
    "--hidden-import", "PyQt6.QtCore",
    "--hidden-import", "PyQt6.QtGui",
    "--hidden-import", "PyQt6.QtWidgets",
    "--hidden-import", "PyQt6.QtSvg",
    "--hidden-import", "PyQt6.QtOpenGLWidgets",
    "--hidden-import", "matplotlib.backends.backend_qtagg",
    "--hidden-import", "numpy",
    "--hidden-import", "grpc",
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

Invoke-ProcessChecked -FilePath $PythonExe -ArgumentList $buildArgs -Label "PyInstaller build"

if (-not (Test-Path $exePath)) {
    throw "Expected executable was not created: $exePath"
}
if (-not (Test-Path $internalFolder)) {
    throw "Expected exposed _internal folder was not created: $internalFolder"
}
foreach ($dllName in $requiredDpfClientDlls) {
    $dllPath = Join-Path $dpfGateBinFolder $dllName
    if (-not (Test-Path $dllPath)) {
        throw "Expected bundled DPF client DLL was not created: $dllPath"
    }
}
foreach ($assetName in $requiredAnimationIconFiles) {
    $assetPath = Join-Path $animationIconBundleFolder $assetName
    if (-not (Test-Path $assetPath)) {
        throw "Expected bundled animation icon asset was not created: $assetPath"
    }
}

Write-Host "Build complete: $exePath"
Write-Host "Keep $AppName.exe beside the exposed _internal folder when copying the app."

if ($SkipSmoke) {
    Write-Host "Packaged smoke skipped."
    exit 0
}

Invoke-PackagedSmoke
