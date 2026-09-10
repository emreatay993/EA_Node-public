[CmdletBinding()]
param(
    [switch]$Clean,
    [switch]$SkipSmoke,
    [switch]$DryRun,
    [switch]$Console,
    [switch]$IncludeIsal,
    [string]$PythonExe = "",
    [string]$AppName = "Office_Date_Collector",
    [string]$DistRoot = "",
    [string]$WorkRoot = "",
    [ValidateRange(5, 120)]
    [int]$SmokeSeconds = 30
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$sourceScript = Join-Path $repoRoot "scripts\office_date_collector_gui.py"
$defaultArtifactRoot = Join-Path $repoRoot "artifacts\pyinstaller\office_date_collector"

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
    foreach ($module in @("PyInstaller", "PyQt6")) {
        if (-not (Test-PythonModule -ModuleName $module)) {
            $missing += $module
        }
    }
    if ($missing.Count -gt 0) {
        throw (
            "The build environment is missing required modules: $($missing -join ', '). " +
            "Install dev dependencies first, for example: " +
            ".\venv\Scripts\python.exe -m pip install -e `".[dev]`""
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
    $process = $null
    try {
        $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
        $startInfo.FileName = $exePath
        $startInfo.WorkingDirectory = $appFolder
        $startInfo.UseShellExecute = $false
        $startInfo.CreateNoWindow = $true
        $startInfo.Arguments = "--self-test"
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
        Write-Host "Packaged smoke passed: self-test completed."
    }
    finally {
        if ($null -ne $process -and -not $process.HasExited) {
            Stop-Process -Id $process.Id -Force
        }
    }
}

Assert-BuildEnvironment
Assert-PathUnderRoot -Path $DistRoot -Root $defaultArtifactRoot -Label "DistRoot"
Assert-PathUnderRoot -Path $WorkRoot -Root $defaultArtifactRoot -Label "WorkRoot"

# python-isal (faster inflate, ~8-11% on the content-search phase per
# scripts\bench_office_search.py) is OFF by default: the default build is kept lean,
# deterministic and free of the native-DLL-after-Qt hazard. Because the source imports
# isal opportunistically, PyInstaller would otherwise auto-bundle it whenever it happens
# to be installed in the venv -- so we explicitly exclude it unless -IncludeIsal is set.
# The app falls back to the stdlib inflate path when isal is absent at runtime.
if ($IncludeIsal) {
    if (-not (Test-PythonModule -ModuleName "isal")) {
        throw "IncludeIsal was requested but 'isal' is not installed. Run: .\venv\Scripts\python.exe -m pip install isal"
    }
    $isalArgs = @("--collect-all", "isal")
    Write-Host "Bundling python-isal (faster inflate) via --collect-all isal."
}
else {
    $isalArgs = @("--exclude-module", "isal")
}

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
    "--hidden-import", "PyQt6.QtCore",
    "--hidden-import", "PyQt6.QtGui",
    "--hidden-import", "PyQt6.QtWidgets",
    "--exclude-module", "PyQt5",
    "--exclude-module", "PySide2",
    "--exclude-module", "PySide6"
) + $isalArgs + @($sourceScript)

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

Write-Host "Build complete: $exePath"
Write-Host "Keep $AppName.exe beside the exposed _internal folder when copying the app."

if ($SkipSmoke) {
    Write-Host "Packaged smoke skipped."
    exit 0
}

Invoke-PackagedSmoke
