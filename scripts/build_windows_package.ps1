[CmdletBinding()]
param(
    [switch]$Clean,
    [switch]$SkipSmoke,
    [switch]$DependencyProbeOnly,
    [ValidateSet("base", "viewer", "web", "full")]
    [string]$PackageProfile = "base",
    [string]$DependencyMatrixPath = "",
    [string]$MarsSourcePath = "..\MARS_",
    [string]$MarsWheelPath = "",
    [ValidateRange(2, 60)]
    [int]$SmokeSeconds = 30
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

$pythonExe = Join-Path $repoRoot "venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    throw "Virtualenv Python was not found at $pythonExe"
}

$specFile = Join-Path $repoRoot "ea_node_editor.spec"
if (-not (Test-Path $specFile)) {
    throw "PyInstaller spec file not found: $specFile"
}

$packageProfileEnvVar = "EA_NODE_EDITOR_PACKAGE_PROFILE"
$packageAppName = "COREX_Node_Editor"
$packageExeName = "$packageAppName.exe"
$runtimeBundleDirName = "runtime"
$runtimeManifestFileName = "runtime_manifest.json"
$runtimeWheelPattern = "corex_node_editor-*.whl"
$artifactRoot = Join-Path $repoRoot "artifacts\pyinstaller"

function Resolve-PyInstallerProfilePath {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("build", "dist")]
        [string]$Kind,
        [Parameter(Mandatory = $true)]
        [ValidateSet("base", "viewer", "web", "full")]
        [string]$Profile
    )
    return Join-Path (Join-Path $artifactRoot $Kind) $Profile
}

function Resolve-PackagedExecutablePath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$DistPath
    )
    return Join-Path (Join-Path $DistPath $packageAppName) $packageExeName
}

function Resolve-PackagedRuntimeBundlePath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$DistPath
    )
    return Join-Path (Join-Path $DistPath $packageAppName) $runtimeBundleDirName
}

function Resolve-LocalRuntimePath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PathValue
    )
    $candidate = if ([System.IO.Path]::IsPathRooted($PathValue)) {
        $PathValue
    }
    else {
        Join-Path $repoRoot $PathValue
    }
    return (Resolve-Path $candidate).Path
}

function Get-WheelPackageMetadata {
    param(
        [Parameter(Mandatory = $true)]
        [string]$WheelPath
    )

    $metadataScript = @'
import json
import sys
import zipfile
from email.parser import Parser

with zipfile.ZipFile(sys.argv[1]) as archive:
    metadata_names = [name for name in archive.namelist() if name.endswith('.dist-info/METADATA')]
    if len(metadata_names) != 1:
        raise SystemExit('wheel must contain exactly one dist-info/METADATA file')
    metadata = Parser().parsestr(archive.read(metadata_names[0]).decode('utf-8'))
print(json.dumps({'distribution': metadata['Name'], 'version': metadata['Version']}))
'@
    $metadataJson = & $pythonExe -c $metadataScript $WheelPath
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to read package metadata from runtime wheel: $WheelPath"
    }
    $metadata = $metadataJson | ConvertFrom-Json
    if ([string]::IsNullOrWhiteSpace($metadata.distribution) -or [string]::IsNullOrWhiteSpace($metadata.version)) {
        throw "Runtime wheel metadata is missing Name or Version: $WheelPath"
    }
    return $metadata
}

function Assert-CorexRuntimeBundle {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RuntimeBundlePath,
        [string]$Label = "Runtime bundle"
    )

    $manifestPath = Join-Path $RuntimeBundlePath $runtimeManifestFileName
    if (-not (Test-Path $manifestPath)) {
        throw "$Label missing runtime manifest: $manifestPath"
    }
    $manifest = Get-Content -Path $manifestPath -Raw | ConvertFrom-Json
    if ($manifest.schema_version -ne 2) {
        throw "$Label runtime manifest schema_version must be 2: $manifestPath"
    }
    foreach ($packageId in @("corex", "mars")) {
        $package = $manifest.packages.$packageId
        if ($null -eq $package) {
            throw "$Label runtime manifest missing package '$packageId': $manifestPath"
        }
        $wheelName = [string]$package.wheel
        if ([string]::IsNullOrWhiteSpace($wheelName) -or [System.IO.Path]::GetFileName($wheelName) -ne $wheelName) {
            throw "$Label runtime package '$packageId' has an invalid bundled wheel name."
        }
        $wheelPath = Join-Path $RuntimeBundlePath $wheelName
        if (-not (Test-Path -Path $wheelPath -PathType Leaf)) {
            throw "$Label runtime package '$packageId' wheel was not found: $wheelPath"
        }
    }
}

function New-CorexRuntimeBundle {
    param(
        [Parameter(Mandatory = $true)]
        [string]$DistPath,
        [Parameter(Mandatory = $true)]
        [ValidateSet("base", "viewer", "web", "full")]
        [string]$Profile
    )

    $runtimeBundlePath = Resolve-PackagedRuntimeBundlePath -DistPath $DistPath
    if (Test-Path $runtimeBundlePath) {
        Remove-Item -Recurse -Force $runtimeBundlePath
    }
    New-Item -ItemType Directory -Path $runtimeBundlePath -Force | Out-Null

    $wheelBuildRoot = Join-Path (Join-Path (Join-Path $repoRoot "artifacts\releases\packaging") $Profile) "runtime_wheels"
    if (Test-Path $wheelBuildRoot) {
        Remove-Item -Recurse -Force $wheelBuildRoot
    }
    New-Item -ItemType Directory -Path $wheelBuildRoot -Force | Out-Null

    $corexWheelBuildRoot = Join-Path $wheelBuildRoot "corex"
    New-Item -ItemType Directory -Path $corexWheelBuildRoot -Force | Out-Null
    $projectRootPath = [System.IO.Path]::GetFullPath([string]$repoRoot)
    $projectRootPrefix = $projectRootPath.TrimEnd([char[]]"\/") + [System.IO.Path]::DirectorySeparatorChar
    $projectBuildPath = [System.IO.Path]::GetFullPath((Join-Path $projectRootPath "build"))
    $expectedProjectBuildPath = $projectRootPrefix + "build"
    if (
        -not $projectBuildPath.StartsWith($projectRootPrefix, [System.StringComparison]::OrdinalIgnoreCase) -or
        -not [string]::Equals($projectBuildPath, $expectedProjectBuildPath, [System.StringComparison]::OrdinalIgnoreCase)
    ) {
        throw "Refusing to clean unexpected COREX wheel build directory: $projectBuildPath"
    }
    if (Test-Path -LiteralPath $projectBuildPath) {
        Remove-Item -LiteralPath $projectBuildPath -Recurse -Force
    }
    $wheelBuildProcess = Start-Process -FilePath $pythonExe -ArgumentList @(
        "-m",
        "build",
        "--wheel",
        "--outdir",
        $corexWheelBuildRoot,
        $repoRoot
    ) -PassThru -Wait -NoNewWindow
    if ($wheelBuildProcess.ExitCode -ne 0) {
        throw "COREX runtime wheel build failed with exit code $($wheelBuildProcess.ExitCode)."
    }

    $runtimeWheel = Get-ChildItem -Path $corexWheelBuildRoot -Filter $runtimeWheelPattern -File | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
    if ($null -eq $runtimeWheel) {
        throw "COREX runtime wheel build did not create a wheel matching $runtimeWheelPattern in $corexWheelBuildRoot"
    }
    Copy-Item -Path $runtimeWheel.FullName -Destination $runtimeBundlePath -Force

    if (-not [string]::IsNullOrWhiteSpace($MarsWheelPath)) {
        $resolvedMarsWheelPath = Resolve-LocalRuntimePath -PathValue $MarsWheelPath
        if ([System.IO.Path]::GetExtension($resolvedMarsWheelPath) -ne ".whl") {
            throw "MARS runtime package must be a local wheel: $resolvedMarsWheelPath"
        }
        $marsRuntimeWheel = Get-Item $resolvedMarsWheelPath
    }
    else {
        $resolvedMarsSourcePath = Resolve-LocalRuntimePath -PathValue $MarsSourcePath
        $marsWheelBuildRoot = Join-Path $wheelBuildRoot "mars"
        New-Item -ItemType Directory -Path $marsWheelBuildRoot -Force | Out-Null
        $marsWheelBuildProcess = Start-Process -FilePath $pythonExe -ArgumentList @(
            "-m",
            "build",
            "--wheel",
            "--outdir",
            $marsWheelBuildRoot,
            $resolvedMarsSourcePath
        ) -PassThru -Wait -NoNewWindow
        if ($marsWheelBuildProcess.ExitCode -ne 0) {
            throw "MARS runtime wheel build failed with exit code $($marsWheelBuildProcess.ExitCode)."
        }
        $marsRuntimeWheels = @(Get-ChildItem -Path $marsWheelBuildRoot -Filter "*.whl" -File)
        if ($marsRuntimeWheels.Count -ne 1) {
            throw "MARS runtime wheel build must create exactly one wheel in $marsWheelBuildRoot"
        }
        $marsRuntimeWheel = $marsRuntimeWheels[0]
    }
    Copy-Item -Path $marsRuntimeWheel.FullName -Destination $runtimeBundlePath -Force

    $corexMetadata = Get-WheelPackageMetadata -WheelPath $runtimeWheel.FullName
    $marsMetadata = Get-WheelPackageMetadata -WheelPath $marsRuntimeWheel.FullName

    $manifest = [ordered]@{
        schema_version = 2
        package_profile = $Profile
        packages = [ordered]@{
            corex = [ordered]@{
                distribution = $corexMetadata.distribution
                version = $corexMetadata.version
                wheel = $runtimeWheel.Name
                extras = @("all")
                required = $true
                console_scripts = @()
            }
            mars = [ordered]@{
                distribution = $marsMetadata.distribution
                version = $marsMetadata.version
                wheel = $marsRuntimeWheel.Name
                extras = @()
                required = $false
                console_scripts = @("MARSBatch")
            }
        }
    }
    $manifestPath = Join-Path $runtimeBundlePath $runtimeManifestFileName
    $manifestJson = $manifest | ConvertTo-Json -Depth 8
    [System.IO.File]::WriteAllText(
        $manifestPath,
        $manifestJson,
        [System.Text.UTF8Encoding]::new($false)
    )
    Assert-CorexRuntimeBundle -RuntimeBundlePath $runtimeBundlePath -Label "Packaged COREX runtime bundle"
    Write-Host "Runtime bundle written: $runtimeBundlePath"
}

function Read-SmokeLog {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path $Path)) {
        return ""
    }
    return Get-Content -Path $Path -Raw -ErrorAction SilentlyContinue
}

function Format-SmokeFailureDetails {
    param(
        [Parameter(Mandatory = $true)]
        [string]$StdoutPath,
        [Parameter(Mandatory = $true)]
        [string]$StderrPath
    )

    $stdout = Read-SmokeLog -Path $StdoutPath
    $stderr = Read-SmokeLog -Path $StderrPath
    $details = @()
    if (-not [string]::IsNullOrWhiteSpace($stdout)) {
        $details += "stdout:`n$stdout"
    }
    if (-not [string]::IsNullOrWhiteSpace($stderr)) {
        $details += "stderr:`n$stderr"
    }
    if ($details.Count -eq 0) {
        return ""
    }
    return "`n" + ($details -join "`n")
}

function Restore-SmokeEnvironmentValue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [AllowNull()]
        [string]$PreviousValue
    )

    if ($null -eq $PreviousValue) {
        Remove-Item "Env:$Name" -ErrorAction SilentlyContinue
    }
    else {
        Set-Item "Env:$Name" $PreviousValue
    }
}

function Invoke-PackagedStartupSmoke {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ExecutablePath,
        [Parameter(Mandatory = $true)]
        [int]$TimeoutSeconds,
        [string]$Label = "Startup smoke test",
        [switch]$SignalPlotRender,
        [switch]$FunctionPlugin
    )

    $stdoutPath = Join-Path $env:TEMP ("corex_startup_smoke_stdout_" + [guid]::NewGuid().ToString("N") + ".log")
    $stderrPath = Join-Path $env:TEMP ("corex_startup_smoke_stderr_" + [guid]::NewGuid().ToString("N") + ".log")
    $previousQtPlatform = $env:QT_QPA_PLATFORM
    $previousProfileStartup = $env:EA_PROFILE_STARTUP
    $previousProfileAutoquit = $env:EA_PROFILE_AUTOQUIT
    $previousSignalPlotSmoke = $env:EA_SIGNAL_PLOT_PACKAGE_SMOKE
    $previousFunctionPluginSmoke = $env:EA_FUNCTION_PLUGIN_PACKAGE_SMOKE
    $process = $null

    try {
        $env:QT_QPA_PLATFORM = "offscreen"
        $env:EA_PROFILE_STARTUP = "1"
        $env:EA_PROFILE_AUTOQUIT = "1"
        if ($SignalPlotRender) {
            $env:EA_SIGNAL_PLOT_PACKAGE_SMOKE = "1"
        }
        else {
            Remove-Item Env:EA_SIGNAL_PLOT_PACKAGE_SMOKE -ErrorAction SilentlyContinue
        }
        if ($FunctionPlugin) {
            $env:EA_FUNCTION_PLUGIN_PACKAGE_SMOKE = "1"
        }
        else {
            Remove-Item Env:EA_FUNCTION_PLUGIN_PACKAGE_SMOKE -ErrorAction SilentlyContinue
        }
        $processStartInfo = [System.Diagnostics.ProcessStartInfo]::new()
        $processStartInfo.FileName = $ExecutablePath
        $processStartInfo.WorkingDirectory = Split-Path $ExecutablePath -Parent
        $processStartInfo.UseShellExecute = $false
        $processStartInfo.CreateNoWindow = $true
        $processStartInfo.RedirectStandardOutput = $true
        $processStartInfo.RedirectStandardError = $true
        $process = [System.Diagnostics.Process]::new()
        $process.StartInfo = $processStartInfo
        [void]$process.Start()
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()

        $completed = $process.WaitForExit($TimeoutSeconds * 1000)
        if (-not $completed) {
            Stop-Process -Id $process.Id -Force
            $process.WaitForExit()
            $stdoutTask.Result | Set-Content -Path $stdoutPath
            $stderrTask.Result | Set-Content -Path $stderrPath
            throw (
                "$Label failed: executable did not complete autoquit startup within $TimeoutSeconds seconds. " +
                "A modal error dialog or startup hang may be blocking the packaged app." +
                (Format-SmokeFailureDetails -StdoutPath $stdoutPath -StderrPath $stderrPath)
            )
        }
        $process.WaitForExit()
        $stdoutTask.Result | Set-Content -Path $stdoutPath
        $stderrTask.Result | Set-Content -Path $stderrPath

        if ($process.ExitCode -ne 0) {
            throw (
                "$Label failed: executable exited with code $($process.ExitCode)." +
                (Format-SmokeFailureDetails -StdoutPath $stdoutPath -StderrPath $stderrPath)
            )
        }

        $combinedLog = (Read-SmokeLog -Path $stdoutPath) + "`n" + (Read-SmokeLog -Path $stderrPath)
        foreach ($marker in @(
            "Traceback (most recent call last):",
            "Unhandled exception",
            "Failed to execute script",
            "FileNotFoundError"
        )) {
            if ($combinedLog -like "*$marker*") {
                throw (
                    "$Label failed: startup log contains '$marker'." +
                    (Format-SmokeFailureDetails -StdoutPath $stdoutPath -StderrPath $stderrPath)
                )
            }
        }

        Write-Host "$Label passed: executable completed autoquit startup within $TimeoutSeconds seconds."
        return $process.ExitCode
    }
    finally {
        if ($null -ne $process -and -not $process.HasExited) {
            Stop-Process -Id $process.Id -Force
        }
        Restore-SmokeEnvironmentValue -Name "QT_QPA_PLATFORM" -PreviousValue $previousQtPlatform
        Restore-SmokeEnvironmentValue -Name "EA_PROFILE_STARTUP" -PreviousValue $previousProfileStartup
        Restore-SmokeEnvironmentValue -Name "EA_PROFILE_AUTOQUIT" -PreviousValue $previousProfileAutoquit
        Restore-SmokeEnvironmentValue -Name "EA_SIGNAL_PLOT_PACKAGE_SMOKE" -PreviousValue $previousSignalPlotSmoke
        Restore-SmokeEnvironmentValue -Name "EA_FUNCTION_PLUGIN_PACKAGE_SMOKE" -PreviousValue $previousFunctionPluginSmoke
        Remove-Item -Path $stdoutPath, $stderrPath -Force -ErrorAction SilentlyContinue
    }
}

$buildDir = Resolve-PyInstallerProfilePath -Kind "build" -Profile $PackageProfile
$distDir = Resolve-PyInstallerProfilePath -Kind "dist" -Profile $PackageProfile

if ($Clean) {
    if (Test-Path $buildDir) {
        Remove-Item -Recurse -Force $buildDir
    }
    if (Test-Path $distDir) {
        Remove-Item -Recurse -Force $distDir
    }
}

New-Item -ItemType Directory -Path $buildDir -Force | Out-Null
New-Item -ItemType Directory -Path $distDir -Force | Out-Null

function Get-DependencyAvailability {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PythonExecutable
    )

    $probeScriptPath = [System.IO.Path]::GetTempFileName()
    $probeOutputPath = Join-Path $env:TEMP ("ea_node_editor_dependency_probe_" + [guid]::NewGuid().ToString("N") + ".json")
    Set-Content -Path $probeScriptPath -Encoding utf8 -Value @"
import importlib.util
import json
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

modules = {
    "imageio_ffmpeg": "imageio_ffmpeg",
    "pypa_build": "build.__main__",
    "duckdb": "duckdb",
    "h5py": "h5py",
    "llvmlite": "llvmlite",
    "numpy": "numpy",
    "numba": "numba",
    "openpyxl": "openpyxl",
    "pandas": "pandas",
    "polars": "polars",
    "psutil": "psutil",
    "pyarrow": "pyarrow",
    "tables": "tables",
    "ansys_mechanical_core": "ansys.mechanical.core",
    "ansys_workbench_core": "ansys.workbench.core",
    "matplotlib": "matplotlib",
    "ocp": "OCP",
    "paramiko": "paramiko",
    "xy": "xy",
    "pyqtgraph": "pyqtgraph",
    "pyvista": "pyvista",
    "pyvistaqt": "pyvistaqt",
    "scipy": "scipy",
    "vtk": "vtkmodules",
    "pyqt6_webengine_core": "PyQt6.QtWebEngineCore",
    "pyqt6_webengine_quick": "PyQt6.QtWebEngineQuick",
    "pyqt6_webengine_widgets": "PyQt6.QtWebEngineWidgets",
    "pyqt6_webchannel": "PyQt6.QtWebChannel",
    "pyqt6_qtmultimedia": "PyQt6.QtMultimedia",
}

def module_available(name):
    try:
        return bool(importlib.util.find_spec(name))
    except (ModuleNotFoundError, ValueError):
        return False

payload = {key: module_available(value) for key, value in modules.items()}
payload["python_major_minor"] = f"{sys.version_info.major}.{sys.version_info.minor}"
try:
    payload["xy_version"] = version("xy")
except PackageNotFoundError:
    payload["xy_version"] = ""
payload["imageio_ffmpeg_binary"] = False
try:
    import imageio_ffmpeg

    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    ffmpeg_result = subprocess.run(
        [ffmpeg_exe, "-version"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    payload["imageio_ffmpeg_binary"] = ffmpeg_result.returncode == 0
except Exception:
    payload["imageio_ffmpeg_binary"] = False
Path(sys.argv[1]).write_text(json.dumps(payload), encoding="utf-8")
"@

    try {
        $probeProcess = Start-Process -FilePath $PythonExecutable -ArgumentList @("-E", $probeScriptPath, $probeOutputPath) -PassThru -Wait
        if ($probeProcess.ExitCode -ne 0) {
            return @{
                duckdb = "unknown"
                imageio_ffmpeg = "unknown"
                imageio_ffmpeg_binary = "unknown"
                pypa_build = "unknown"
                h5py = "unknown"
                llvmlite = "unknown"
                numpy = "unknown"
                numba = "unknown"
                openpyxl = "unknown"
                pandas = "unknown"
                polars = "unknown"
                psutil = "unknown"
                pyarrow = "unknown"
                tables = "unknown"
                ansys_mechanical_core = "unknown"
                matplotlib = "unknown"
                ocp = "unknown"
                paramiko = "unknown"
                xy = "unknown"
                pyqtgraph = "unknown"
                pyvista = "unknown"
                pyvistaqt = "unknown"
                scipy = "unknown"
                vtk = "unknown"
                pyqt6_webengine_core = "unknown"
                pyqt6_webengine_quick = "unknown"
                pyqt6_webengine_widgets = "unknown"
                pyqt6_webchannel = "unknown"
                pyqt6_qtmultimedia = "unknown"
            }
        }
        if (-not (Test-Path $probeOutputPath)) {
            return @{
                duckdb = "unknown"
                imageio_ffmpeg = "unknown"
                imageio_ffmpeg_binary = "unknown"
                pypa_build = "unknown"
                h5py = "unknown"
                llvmlite = "unknown"
                numpy = "unknown"
                numba = "unknown"
                openpyxl = "unknown"
                pandas = "unknown"
                polars = "unknown"
                psutil = "unknown"
                pyarrow = "unknown"
                tables = "unknown"
                ansys_mechanical_core = "unknown"
                matplotlib = "unknown"
                ocp = "unknown"
                paramiko = "unknown"
                xy = "unknown"
                pyqtgraph = "unknown"
                pyvista = "unknown"
                pyvistaqt = "unknown"
                scipy = "unknown"
                vtk = "unknown"
                pyqt6_webengine_core = "unknown"
                pyqt6_webengine_quick = "unknown"
                pyqt6_webengine_widgets = "unknown"
                pyqt6_webchannel = "unknown"
                pyqt6_qtmultimedia = "unknown"
            }
        }
        $parsed = Get-Content -Path $probeOutputPath -Raw | ConvertFrom-Json
        return @{
            python_major_minor = [string]$parsed.python_major_minor
            xy_version = [string]$parsed.xy_version
            pypa_build = [bool]$parsed.pypa_build
            duckdb = [bool]$parsed.duckdb
            imageio_ffmpeg = [bool]$parsed.imageio_ffmpeg
            imageio_ffmpeg_binary = [bool]$parsed.imageio_ffmpeg_binary
            h5py = [bool]$parsed.h5py
            llvmlite = [bool]$parsed.llvmlite
            numpy = [bool]$parsed.numpy
            numba = [bool]$parsed.numba
            openpyxl = [bool]$parsed.openpyxl
            pandas = [bool]$parsed.pandas
            polars = [bool]$parsed.polars
            psutil = [bool]$parsed.psutil
            pyarrow = [bool]$parsed.pyarrow
            tables = [bool]$parsed.tables
            ansys_mechanical_core = [bool]$parsed.ansys_mechanical_core
            matplotlib = [bool]$parsed.matplotlib
            ocp = [bool]$parsed.ocp
            paramiko = [bool]$parsed.paramiko
            xy = [bool]$parsed.xy
            pyqtgraph = [bool]$parsed.pyqtgraph
            pyvista = [bool]$parsed.pyvista
            pyvistaqt = [bool]$parsed.pyvistaqt
            scipy = [bool]$parsed.scipy
            vtk = [bool]$parsed.vtk
            pyqt6_webengine_core = [bool]$parsed.pyqt6_webengine_core
            pyqt6_webengine_quick = [bool]$parsed.pyqt6_webengine_quick
            pyqt6_webengine_widgets = [bool]$parsed.pyqt6_webengine_widgets
            pyqt6_webchannel = [bool]$parsed.pyqt6_webchannel
            pyqt6_qtmultimedia = [bool]$parsed.pyqt6_qtmultimedia
        }
    }
    catch {
        return @{
            duckdb = "unknown"
            imageio_ffmpeg = "unknown"
            imageio_ffmpeg_binary = "unknown"
            pypa_build = "unknown"
            h5py = "unknown"
            llvmlite = "unknown"
            numpy = "unknown"
            numba = "unknown"
            openpyxl = "unknown"
            pandas = "unknown"
            polars = "unknown"
            psutil = "unknown"
            pyarrow = "unknown"
            tables = "unknown"
            ansys_mechanical_core = "unknown"
            matplotlib = "unknown"
            ocp = "unknown"
            paramiko = "unknown"
            xy = "unknown"
            pyqtgraph = "unknown"
            pyvista = "unknown"
            pyvistaqt = "unknown"
            scipy = "unknown"
            vtk = "unknown"
            pyqt6_webengine_core = "unknown"
            pyqt6_webengine_quick = "unknown"
            pyqt6_webengine_widgets = "unknown"
            pyqt6_webchannel = "unknown"
            pyqt6_qtmultimedia = "unknown"
        }
    }
    finally {
        Remove-Item -Path $probeScriptPath, $probeOutputPath -Force -ErrorAction SilentlyContinue
    }
}

function Assert-PackageProfileDependencies {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("base", "viewer", "web", "full")]
        [string]$Profile,
        [Parameter(Mandatory = $true)]
        [hashtable]$Availability
    )

    $requiredModules = Get-PackageProfileDependencyRules -Profile $Profile

    if ($Availability.python_major_minor -ne "3.11") {
        throw "Packaging requires Python 3.11 exactly; found $($Availability.python_major_minor)."
    }
    if ($Availability.xy_version -ne "0.0.6") {
        throw "Packaging requires xy==0.0.6 exactly; found $($Availability.xy_version)."
    }

    $missing = @()
    foreach ($module in $requiredModules) {
        if ($Availability[$module.Key] -ne $true) {
            $missing += $module.Display
        }
    }

    if ($missing.Count -gt 0) {
        throw (
            "$Profile package profile requires all core runtime modules plus any profile-specific optional extras. " +
            "Install the project requirements before packaging. Missing: $($missing -join ', ')."
        )
    }
}

function Get-PackageProfileDependencyRules {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("base", "viewer", "web", "full")]
        [string]$Profile
    )

    $required = @(
        @{ Key = "pypa_build"; Display = "build" },
        @{ Key = "paramiko"; Display = "paramiko" },
        @{ Key = "xy"; Display = "xy==0.0.6" },
        @{ Key = "pyqt6_webengine_core"; Display = "PyQt6.QtWebEngineCore" },
        @{ Key = "pyqt6_webengine_quick"; Display = "PyQt6.QtWebEngineQuick" },
        @{ Key = "pyqt6_webengine_widgets"; Display = "PyQt6.QtWebEngineWidgets" },
        @{ Key = "pyqt6_webchannel"; Display = "PyQt6.QtWebChannel" },
        @{ Key = "pyqt6_qtmultimedia"; Display = "PyQt6.QtMultimedia" },
        @{ Key = "imageio_ffmpeg"; Display = "imageio-ffmpeg" },
        @{ Key = "imageio_ffmpeg_binary"; Display = "imageio-ffmpeg bundled ffmpeg" }
    )

    if ($Profile -eq "viewer" -or $Profile -eq "full") {
        $required += @(
            @{ Key = "ocp"; Display = "cadquery-ocp-novtk" },
            @{ Key = "pyvista"; Display = "pyvista" },
            @{ Key = "pyvistaqt"; Display = "pyvistaqt" },
            @{ Key = "vtk"; Display = "vtk" }
        )
    }

    if ($Profile -eq "full") {
        $required += @(
            @{ Key = "ansys_mechanical_core"; Display = "ansys-mechanical-core" },
            @{ Key = "ansys_workbench_core"; Display = "ansys-workbench-core" },
            @{ Key = "duckdb"; Display = "duckdb" },
            @{ Key = "h5py"; Display = "h5py" },
            @{ Key = "llvmlite"; Display = "llvmlite" },
            @{ Key = "matplotlib"; Display = "matplotlib" },
            @{ Key = "numba"; Display = "numba" },
            @{ Key = "numpy"; Display = "numpy" },
            @{ Key = "openpyxl"; Display = "openpyxl" },
            @{ Key = "pandas"; Display = "pandas" },
            @{ Key = "polars"; Display = "polars" },
            @{ Key = "psutil"; Display = "psutil" },
            @{ Key = "pyarrow"; Display = "pyarrow" },
            @{ Key = "pyqtgraph"; Display = "pyqtgraph" },
            @{ Key = "scipy"; Display = "scipy" },
            @{ Key = "tables"; Display = "tables" }
        )
    }

    return $required
}

function Write-DependencyMatrix {
    param(
        [Parameter(Mandatory = $true)]
        [string]$OutputPath,
        [Parameter(Mandatory = $true)]
        [hashtable]$Availability,
        [Parameter(Mandatory = $true)]
        [ValidateSet("base", "viewer", "web", "full")]
        [string]$Profile
    )

    $isFullProfile = $Profile -eq "full"
    $viewerPackagedBehavior = if ($Profile -eq "viewer") {
        "Viewer profile bundles the neutral CAD/FE viewer runtime and fails the build when missing from the build environment."
    }
    elseif ($isFullProfile) {
        "Full profile bundles the application runtime stack, including PyMechanical, viewer, tabular, acceleration, Excel, and plot backends."
    }
    else {
        "Base/web profiles exclude the viewer runtime stack to keep packaged builds lean."
    }
    $viewerPackagingPolicy = if ($Profile -eq "viewer") {
        "Viewer profile only; required when building the viewer-enabled packaged app."
    }
    elseif ($isFullProfile) {
        "Full profile required dependency; missing install fails the build."
    }
    else {
        "Excluded from base/web package profiles."
    }
    $viewerOperatorAction = if ($isFullProfile) {
        "Install the all/dev dependency stack before running a full-profile package build."
    }
    else {
        "Install the viewer extra before running a viewer-profile package build."
    }
    $webPackagedBehavior = "All package profiles bundle the local WebEngine/WebChannel runtime and fail the build when missing from the build environment."
    $tabularPackagedBehavior = if ($isFullProfile) {
        "Full profile bundles every tabular backend from the all/dev dependency stack and fails the build when missing."
    }
    else {
        "Tabular Data stays optional; packages include discovered tabular backends only when present in the build environment."
    }
    $tabularPackagingPolicy = if ($isFullProfile) {
        "Full profile required dependency; missing install fails the build."
    }
    else {
        "Optional include; bundled only if present in build environment."
    }
    $tabularOperatorAction = if ($isFullProfile) {
        "Install the all/dev dependency stack before running a full-profile package build."
    }
    else {
        "Install the tabular extra before packaging when tabular workflows are required."
    }
    $excelPackagedBehavior = if ($isFullProfile) {
        "Full profile bundles the Excel backend and fails the build when missing from the build environment."
    }
    else {
        "Same node behavior in packaged app; missing dependency message instructs rebuild with openpyxl in build environment."
    }
    $excelPackagingPolicy = if ($isFullProfile) {
        "Full profile required dependency; missing install fails the build."
    }
    else {
        "Optional include; bundled only if present in build environment."
    }
    $excelOperatorAction = if ($isFullProfile) {
        "Install the all/dev dependency stack before running a full-profile package build."
    }
    else {
        "Install openpyxl before packaging when XLSX workflows are required."
    }
    $accelerationPackagedBehavior = if ($isFullProfile) {
        "Full profile bundles the Numba acceleration backend and fails the build when missing."
    }
    else {
        "Numba acceleration is bundled only when present in the build environment."
    }
    $accelerationPackagingPolicy = if ($isFullProfile) {
        "Full profile required dependency; missing install fails the build."
    }
    else {
        "Optional include; bundled only if present in build environment."
    }
    $accelerationOperatorAction = if ($isFullProfile) {
        "Install the all/dev dependency stack before running a full-profile package build."
    }
    else {
        "Install the acceleration extra before packaging when Numba-backed workflows are required."
    }
    $webEngineInstalled = (
        $Availability.pyqt6_webengine_core -eq $true -and
        $Availability.pyqt6_webengine_quick -eq $true -and
        $Availability.pyqt6_webengine_widgets -eq $true
    )

    $rows = @(
        [PSCustomObject]@{
            package_profile = $Profile
            dependency_group = "packaging"
            dependency = "build"
            build_env_installed = $Availability.pypa_build
            source_runtime_behavior = "The packaging script needs PyPA build to create the managed COREX runtime wheel."
            packaged_runtime_behavior = "Not bundled into the frozen app; required in the build environment before packaging starts."
            packaging_policy = "Required packaging tool for every package profile."
            operator_action = "Install the dev extra or run python -m pip install build before packaging."
        },
        [PSCustomObject]@{
            package_profile = $Profile
            dependency_group = "excel"
            dependency = "openpyxl"
            build_env_installed = $Availability.openpyxl
            source_runtime_behavior = "Excel Read/Write: CSV always works; XLSX requires openpyxl and emits deterministic RuntimeError when unavailable."
            packaged_runtime_behavior = $excelPackagedBehavior
            packaging_policy = $excelPackagingPolicy
            operator_action = $excelOperatorAction
        },
        [PSCustomObject]@{
            package_profile = $Profile
            dependency_group = "tabular"
            dependency = "numpy"
            build_env_installed = $Availability.numpy
            source_runtime_behavior = "Tabular Data add-on remains unavailable until the optional tabular extra is installed."
            packaged_runtime_behavior = $tabularPackagedBehavior
            packaging_policy = $tabularPackagingPolicy
            operator_action = $tabularOperatorAction
        },
        [PSCustomObject]@{
            package_profile = $Profile
            dependency_group = "tabular"
            dependency = "pandas"
            build_env_installed = $Availability.pandas
            source_runtime_behavior = "Tabular Data add-on remains unavailable until the optional tabular extra is installed."
            packaged_runtime_behavior = $tabularPackagedBehavior
            packaging_policy = $tabularPackagingPolicy
            operator_action = $tabularOperatorAction
        },
        [PSCustomObject]@{
            package_profile = $Profile
            dependency_group = "tabular"
            dependency = "polars"
            build_env_installed = $Availability.polars
            source_runtime_behavior = "Tabular Data add-on remains unavailable until the optional tabular extra is installed."
            packaged_runtime_behavior = $tabularPackagedBehavior
            packaging_policy = $tabularPackagingPolicy
            operator_action = $tabularOperatorAction
        },
        [PSCustomObject]@{
            package_profile = $Profile
            dependency_group = "tabular"
            dependency = "pyarrow"
            build_env_installed = $Availability.pyarrow
            source_runtime_behavior = "Tabular Data add-on remains unavailable until the optional tabular extra is installed."
            packaged_runtime_behavior = $tabularPackagedBehavior
            packaging_policy = $tabularPackagingPolicy
            operator_action = $tabularOperatorAction
        },
        [PSCustomObject]@{
            package_profile = $Profile
            dependency_group = "tabular"
            dependency = "duckdb"
            build_env_installed = $Availability.duckdb
            source_runtime_behavior = "Tabular Data add-on remains unavailable until the optional tabular extra is installed."
            packaged_runtime_behavior = $tabularPackagedBehavior
            packaging_policy = $tabularPackagingPolicy
            operator_action = $tabularOperatorAction
        },
        [PSCustomObject]@{
            package_profile = $Profile
            dependency_group = "tabular"
            dependency = "openpyxl"
            build_env_installed = $Availability.openpyxl
            source_runtime_behavior = "Tabular Data add-on remains unavailable until the optional tabular extra is installed."
            packaged_runtime_behavior = $tabularPackagedBehavior
            packaging_policy = $tabularPackagingPolicy
            operator_action = $tabularOperatorAction
        },
        [PSCustomObject]@{
            package_profile = $Profile
            dependency_group = "tabular"
            dependency = "h5py"
            build_env_installed = $Availability.h5py
            source_runtime_behavior = "Tabular Data add-on remains unavailable until the optional tabular extra is installed."
            packaged_runtime_behavior = $tabularPackagedBehavior
            packaging_policy = $tabularPackagingPolicy
            operator_action = $tabularOperatorAction
        },
        [PSCustomObject]@{
            package_profile = $Profile
            dependency_group = "acceleration"
            dependency = "numba"
            build_env_installed = $Availability.numba
            source_runtime_behavior = "Numba is an optional runtime acceleration backend for Pandas and user-authored numerical workflows."
            packaged_runtime_behavior = $accelerationPackagedBehavior
            packaging_policy = $accelerationPackagingPolicy
            operator_action = $accelerationOperatorAction
        },
        [PSCustomObject]@{
            package_profile = $Profile
            dependency_group = "acceleration"
            dependency = "llvmlite"
            build_env_installed = $Availability.llvmlite
            source_runtime_behavior = "llvmlite is the native LLVM runtime companion installed by Numba."
            packaged_runtime_behavior = $accelerationPackagedBehavior
            packaging_policy = $accelerationPackagingPolicy
            operator_action = $accelerationOperatorAction
        },
        [PSCustomObject]@{
            package_profile = $Profile
            dependency_group = "tabular"
            dependency = "tables"
            build_env_installed = $Availability.tables
            source_runtime_behavior = "Tabular Data add-on remains unavailable until the optional tabular extra is installed."
            packaged_runtime_behavior = $tabularPackagedBehavior
            packaging_policy = $tabularPackagingPolicy
            operator_action = $tabularOperatorAction
        },
        [PSCustomObject]@{
            package_profile = $Profile
            dependency_group = "core"
            dependency = "psutil"
            build_env_installed = $Availability.psutil
            source_runtime_behavior = "System metrics require psutil for live CPU and RAM readings."
            packaged_runtime_behavior = "Packaged app must include psutil so the telemetry strip remains live."
            packaging_policy = "Required dependency; missing install is a packaging defect."
            operator_action = "Install psutil before packaging."
        },
        [PSCustomObject]@{
            package_profile = $Profile
            dependency_group = "core"
            dependency = "scipy"
            build_env_installed = $Availability.scipy
            source_runtime_behavior = "SciPy is part of the project runtime dependency set for engineering workflows and user scripts."
            packaged_runtime_behavior = if ($isFullProfile) { "Full profile bundles SciPy from the all/dev dependency stack." } else { "Available when present in the packaging environment." }
            packaging_policy = if ($isFullProfile) { "Full profile required dependency; missing install fails the build." } else { "Project dependency; install project requirements before packaging." }
            operator_action = if ($isFullProfile) { "Install the all/dev dependency stack before running a full-profile package build." } else { "Install project requirements before packaging." }
        },
        [PSCustomObject]@{
            package_profile = $Profile
            dependency_group = "web"
            dependency = "PyQt6-WebEngine"
            build_env_installed = $webEngineInstalled
            source_runtime_behavior = "WebEngine-backed web surfaces require the core PyQt6-WebEngine runtime; headless/offscreen sessions use the deterministic fallback."
            packaged_runtime_behavior = $webPackagedBehavior
            packaging_policy = "Required dependency for every package profile."
            operator_action = "Install project requirements before packaging."
        },
        [PSCustomObject]@{
            package_profile = $Profile
            dependency_group = "web"
            dependency = "PyQt6.QtWebChannel"
            build_env_installed = $Availability.pyqt6_webchannel
            source_runtime_behavior = "Qt WebChannel is required by the local WebEngine host bridge."
            packaged_runtime_behavior = $webPackagedBehavior
            packaging_policy = "Required dependency for every package profile."
            operator_action = "Install project requirements before packaging."
        },
        [PSCustomObject]@{
            package_profile = $Profile
            dependency_group = "media"
            dependency = "PyQt6.QtMultimedia"
            build_env_installed = $Availability.pyqt6_qtmultimedia
            source_runtime_behavior = "Media Panel video mode uses Qt Multimedia MediaPlayer, VideoOutput, and AudioOutput."
            packaged_runtime_behavior = "All package profiles bundle the Qt Multimedia runtime and fail the build when missing from the build environment."
            packaging_policy = "Required dependency for every package profile."
            operator_action = "Install project requirements before packaging."
        },
        [PSCustomObject]@{
            package_profile = $Profile
            dependency_group = "media"
            dependency = "imageio-ffmpeg"
            build_env_installed = ($Availability.imageio_ffmpeg -eq $true -and $Availability.imageio_ffmpeg_binary -eq $true)
            source_runtime_behavior = "Media Panel video-mode trim-save uses imageio-ffmpeg to locate a bundled ffmpeg executable for internal MP4 clip creation."
            packaged_runtime_behavior = "All package profiles bundle imageio-ffmpeg and its ffmpeg executable for Media Panel video-mode trim-save."
            packaging_policy = "Required dependency for every package profile."
            operator_action = "Install project requirements before packaging."
        },
        [PSCustomObject]@{
            package_profile = $Profile
            dependency_group = "ssh_sftp"
            dependency = "paramiko"
            build_env_installed = $Availability.paramiko
            source_runtime_behavior = "Built-in SSH/SFTP nodes require Paramiko."
            packaged_runtime_behavior = "All package profiles bundle Paramiko for built-in SSH/SFTP nodes and fail the build when it is missing."
            packaging_policy = "Required dependency for every package profile."
            operator_action = "Install project requirements before packaging."
        },
        [PSCustomObject]@{
            package_profile = $Profile
            dependency_group = "plot"
            dependency = "xy==0.0.6"
            build_env_installed = $Availability.xy
            source_runtime_behavior = "Signal Plot uses XY's browser-free native PNG renderer."
            packaged_runtime_behavior = "Every package profile bundles XY and its native xy_core library."
            packaging_policy = "Required dependency for every package profile."
            operator_action = "Install project requirements before packaging."
        },
        [PSCustomObject]@{
            package_profile = $Profile
            dependency_group = "plot"
            dependency = "matplotlib"
            build_env_installed = $Availability.matplotlib
            source_runtime_behavior = "Matplotlib backs headless/static plot export and remains unavailable until the viewer/runtime extra is installed."
            packaged_runtime_behavior = if ($isFullProfile) { "Full profile bundles the Matplotlib plot backend and fails the build when missing." } else { "Plot backend support is bundled only when Matplotlib is present in the build environment." }
            packaging_policy = if ($isFullProfile) { "Full profile required dependency; missing install fails the build." } else { "Optional include; bundled only if present in build environment." }
            operator_action = if ($isFullProfile) { "Install the all/dev dependency stack before running a full-profile package build." } else { "Install the viewer extra before packaging when plot workflows are required." }
        },
        [PSCustomObject]@{
            package_profile = $Profile
            dependency_group = "plot"
            dependency = "pyqtgraph"
            build_env_installed = $Availability.pyqtgraph
            source_runtime_behavior = "PyQtGraph backs live 2D plot widgets and remains unavailable until the viewer/runtime extra is installed."
            packaged_runtime_behavior = if ($isFullProfile) { "Full profile bundles the PyQtGraph plot backend and fails the build when missing." } else { "Plot backend support is bundled only when PyQtGraph is present in the build environment." }
            packaging_policy = if ($isFullProfile) { "Full profile required dependency; missing install fails the build." } else { "Optional include; bundled only if present in build environment." }
            operator_action = if ($isFullProfile) { "Install the all/dev dependency stack before running a full-profile package build." } else { "Install the viewer extra before packaging when plot workflows are required." }
        },
        [PSCustomObject]@{
            package_profile = $Profile
            dependency_group = "ansys"
            dependency = "ansys-mechanical-core"
            build_env_installed = $Availability.ansys_mechanical_core
            source_runtime_behavior = "PyMechanical is part of the Ansys optional runtime stack."
            packaged_runtime_behavior = if ($isFullProfile) { "Full profile bundles ansys-mechanical-core and fails the build when missing." } else { "PyMechanical is bundled only when present in the build environment." }
            packaging_policy = if ($isFullProfile) { "Full profile required dependency; missing install fails the build." } else { "Optional include; bundled only if present in build environment." }
            operator_action = if ($isFullProfile) { "Install the all/dev dependency stack before running a full-profile package build." } else { "Install the ansys extra before packaging when PyMechanical workflows are required." }
        },
        [PSCustomObject]@{
            package_profile = $Profile
            dependency_group = "ansys"
            dependency = "ansys-workbench-core"
            build_env_installed = $Availability.ansys_workbench_core
            source_runtime_behavior = "PyWorkbench retains native Workbench project ownership for Mechanical catalogue runs."
            packaged_runtime_behavior = if ($isFullProfile) { "Full profile bundles ansys-workbench-core and fails the build when missing." } else { "PyWorkbench is bundled only when present in the build environment." }
            packaging_policy = if ($isFullProfile) { "Full profile required dependency; missing install fails the build." } else { "Optional include; bundled only if present in build environment." }
            operator_action = if ($isFullProfile) { "Install the all/dev dependency stack before running a full-profile package build." } else { "Install the ansys extra before packaging when Workbench workflows are required." }
        },
        [PSCustomObject]@{
            package_profile = $Profile
            dependency_group = "viewer"
            dependency = "cadquery-ocp-novtk"
            build_env_installed = $Availability.ocp
            source_runtime_behavior = "OCP provides neutral STEP/BREP CAD import for Model Viewer workflows."
            packaged_runtime_behavior = $viewerPackagedBehavior
            packaging_policy = $viewerPackagingPolicy
            operator_action = $viewerOperatorAction
        },
        [PSCustomObject]@{
            package_profile = $Profile
            dependency_group = "viewer"
            dependency = "pyvista"
            build_env_installed = $Availability.pyvista
            source_runtime_behavior = "PyVista-backed mesh materialization stays optional until export or viewer rendering is requested."
            packaged_runtime_behavior = $viewerPackagedBehavior
            packaging_policy = $viewerPackagingPolicy
            operator_action = $viewerOperatorAction
        },
        [PSCustomObject]@{
            package_profile = $Profile
            dependency_group = "viewer"
            dependency = "pyvistaqt"
            build_env_installed = $Availability.pyvistaqt
            source_runtime_behavior = "PyVistaQt stays optional until Qt-hosted viewer surfaces are requested."
            packaged_runtime_behavior = $viewerPackagedBehavior
            packaging_policy = $viewerPackagingPolicy
            operator_action = $viewerOperatorAction
        },
        [PSCustomObject]@{
            package_profile = $Profile
            dependency_group = "viewer"
            dependency = "vtk"
            build_env_installed = $Availability.vtk
            source_runtime_behavior = "VTK stays optional until PyVista materialization or viewer rendering loads VTK modules."
            packaged_runtime_behavior = $viewerPackagedBehavior
            packaging_policy = $viewerPackagingPolicy
            operator_action = $viewerOperatorAction
        }
    )

    $outputDir = Split-Path -Parent $OutputPath
    if ($outputDir) {
        New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
    }
    $rows | Export-Csv -Path $OutputPath -NoTypeInformation -Encoding utf8
}

$dependencyAvailability = Get-DependencyAvailability -PythonExecutable $pythonExe
Assert-PackageProfileDependencies -Profile $PackageProfile -Availability $dependencyAvailability

if ([string]::IsNullOrWhiteSpace($DependencyMatrixPath)) {
    $DependencyMatrixPath = "artifacts\releases\packaging\$PackageProfile\dependency_matrix.csv"
}

$dependencyMatrixFullPath = if ([System.IO.Path]::IsPathRooted($DependencyMatrixPath)) {
    $DependencyMatrixPath
}
else {
    Join-Path $repoRoot $DependencyMatrixPath
}
Write-DependencyMatrix -OutputPath $dependencyMatrixFullPath -Availability $dependencyAvailability -Profile $PackageProfile
Write-Host "Dependency matrix written: $dependencyMatrixFullPath"
if ($DependencyProbeOnly) {
    Write-Host "Dependency probe passed: Python 3.11 and xy==0.0.6."
    exit 0
}

$buildArgs = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--workpath", $buildDir,
    "--distpath", $distDir,
    $specFile
)

$previousPackageProfile = [System.Environment]::GetEnvironmentVariable($packageProfileEnvVar, "Process")
Write-Host "Building Windows package with PyInstaller (profile: $PackageProfile)..."
try {
    [System.Environment]::SetEnvironmentVariable($packageProfileEnvVar, $PackageProfile, "Process")
    $buildProcess = Start-Process -FilePath $pythonExe -ArgumentList $buildArgs -PassThru -Wait -NoNewWindow
    if ($buildProcess.ExitCode -ne 0) {
        throw "PyInstaller build failed with exit code $($buildProcess.ExitCode)."
    }
}
finally {
    [System.Environment]::SetEnvironmentVariable($packageProfileEnvVar, $previousPackageProfile, "Process")
}

$exePath = Resolve-PackagedExecutablePath -DistPath $distDir
if (-not (Test-Path $exePath)) {
    throw "Expected executable was not created: $exePath"
}

New-CorexRuntimeBundle -DistPath $distDir -Profile $PackageProfile

Write-Host "Build complete: $exePath"

if ($SkipSmoke) {
    Write-Host "Smoke tests skipped; this build is not acceptance evidence."
    exit 0
}

Write-Host "Running startup smoke test (timeout: $SmokeSeconds s)..."
Invoke-PackagedStartupSmoke -ExecutablePath $exePath -TimeoutSeconds $SmokeSeconds | Out-Null
Write-Host "Running function plugin process-worker smoke test (timeout: $SmokeSeconds s)..."
Invoke-PackagedStartupSmoke -ExecutablePath $exePath -TimeoutSeconds $SmokeSeconds -Label "Function plugin execution smoke test" -FunctionPlugin | Out-Null
Write-Host "Running native Signal Plot PNG smoke test (timeout: $SmokeSeconds s)..."
Invoke-PackagedStartupSmoke -ExecutablePath $exePath -TimeoutSeconds $SmokeSeconds -Label "Signal Plot render smoke test" -SignalPlotRender | Out-Null
