[CmdletBinding()]
param(
    [ValidateSet("base", "viewer", "web", "full")]
    [string]$PackageProfile = "base",
    [string]$DistPath = "",
    [string]$OutputRoot = "",
    [ValidateRange(2, 60)]
    [int]$SmokeSeconds = 30
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

$packageAppName = "COREX_Node_Editor"
$packageExeName = "$packageAppName.exe"
$runtimeBundleDirName = "runtime"
$runtimeManifestFileName = "runtime_manifest.json"
$pyInstallerArtifactRoot = Join-Path $repoRoot "artifacts\pyinstaller"
$releaseArtifactRoot = Join-Path $repoRoot "artifacts\releases"

function Resolve-PowerShellHostPath {
    $candidateNames = @(
        "powershell.exe",
        "pwsh.exe",
        "powershell",
        "pwsh"
    )

    foreach ($candidateName in $candidateNames) {
        try {
            $command = Get-Command $candidateName -ErrorAction Stop
            if (-not [string]::IsNullOrWhiteSpace($command.Source)) {
                return $command.Source
            }
            if (-not [string]::IsNullOrWhiteSpace($command.Path)) {
                return $command.Path
            }
            return $candidateName
        }
        catch {
            continue
        }
    }

    foreach ($candidatePath in @((Join-Path $PSHOME "powershell.exe"), (Join-Path $PSHOME "pwsh.exe"))) {
        if (Test-Path $candidatePath) {
            return $candidatePath
        }
    }

    throw "Unable to resolve a PowerShell host for installer validation."
}

function Invoke-PowerShellScriptFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$HostPath,
        [Parameter(Mandatory = $true)]
        [string]$ScriptPath,
        [Parameter(Mandatory = $true)]
        [string]$InstallRoot
    )

    $childProcess = Start-Process -FilePath $HostPath -ArgumentList @(
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        $ScriptPath,
        "-InstallRoot",
        $InstallRoot
    ) -PassThru -Wait -NoNewWindow
    if ($childProcess.ExitCode -ne 0) {
        throw "PowerShell child host failed for script: $ScriptPath"
    }
}

function New-InstallerBundleZip {
    param(
        [Parameter(Mandatory = $true)]
        [string]$BundleRoot,
        [Parameter(Mandatory = $true)]
        [string]$DestinationPath
    )

    $tarCommand = Get-Command "tar.exe" -ErrorAction SilentlyContinue
    if ($null -ne $tarCommand) {
        $tarProcess = Start-Process -FilePath $tarCommand.Source -ArgumentList @(
            "-a",
            "-cf",
            $DestinationPath,
            "-C",
            $BundleRoot,
            "payload",
            "scripts"
        ) -PassThru -Wait -NoNewWindow
        if ($tarProcess.ExitCode -ne 0) {
            throw "tar.exe failed with exit code $($tarProcess.ExitCode)."
        }
        if (-not (Test-Path $DestinationPath)) {
            throw "tar.exe did not create installer bundle: $DestinationPath"
        }
        if ((Get-Item $DestinationPath).Length -le 0) {
            throw "tar.exe created an empty installer bundle: $DestinationPath"
        }
        return
    }

    Compress-Archive -Path (Join-Path $BundleRoot "payload"), (Join-Path $BundleRoot "scripts") -DestinationPath $DestinationPath -Force
    if (-not (Test-Path $DestinationPath)) {
        throw "Compress-Archive did not create installer bundle: $DestinationPath"
    }
    if ((Get-Item $DestinationPath).Length -le 0) {
        throw "Compress-Archive created an empty installer bundle: $DestinationPath"
    }
}

function Resolve-RepoPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PathValue
    )
    if ([System.IO.Path]::IsPathRooted($PathValue)) {
        return $PathValue
    }
    return Join-Path $repoRoot $PathValue
}

function Resolve-PyInstallerDistPath {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("base", "viewer", "web", "full")]
        [string]$Profile
    )
    return Join-Path (Join-Path (Join-Path $pyInstallerArtifactRoot "dist") $Profile) $packageAppName
}

function Resolve-PackagedExecutablePath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$DistPath
    )
    return Join-Path $DistPath $packageExeName
}

function Assert-CorexRuntimeBundlePayload {
    param(
        [Parameter(Mandatory = $true)]
        [string]$AppRoot,
        [string]$Label = "Runtime bundle"
    )

    $runtimeBundlePath = Join-Path $AppRoot $runtimeBundleDirName
    if (-not (Test-Path $runtimeBundlePath)) {
        throw "$Label missing runtime bundle directory: $runtimeBundlePath"
    }
    $manifestPath = Join-Path $runtimeBundlePath $runtimeManifestFileName
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
        $wheelPath = Join-Path $runtimeBundlePath $wheelName
        if (-not (Test-Path -Path $wheelPath -PathType Leaf)) {
            throw "$Label runtime package '$packageId' wheel was not found: $wheelPath"
        }
    }
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
        [string]$Label = "Installed executable smoke test"
    )

    $stdoutPath = Join-Path $env:TEMP ("corex_startup_smoke_stdout_" + [guid]::NewGuid().ToString("N") + ".log")
    $stderrPath = Join-Path $env:TEMP ("corex_startup_smoke_stderr_" + [guid]::NewGuid().ToString("N") + ".log")
    $previousQtPlatform = $env:QT_QPA_PLATFORM
    $previousProfileStartup = $env:EA_PROFILE_STARTUP
    $previousProfileAutoquit = $env:EA_PROFILE_AUTOQUIT
    $process = $null

    try {
        $env:QT_QPA_PLATFORM = "offscreen"
        $env:EA_PROFILE_STARTUP = "1"
        $env:EA_PROFILE_AUTOQUIT = "1"
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
        Remove-Item -Path $stdoutPath, $stderrPath -Force -ErrorAction SilentlyContinue
    }
}

function Resolve-InstallerOutputRoot {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("base", "viewer", "web", "full")]
        [string]$Profile
    )
    return Join-Path (Join-Path $releaseArtifactRoot "installer") $Profile
}

if ([string]::IsNullOrWhiteSpace($DistPath)) {
    $DistPath = Resolve-PyInstallerDistPath -Profile $PackageProfile
}
if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $OutputRoot = Resolve-InstallerOutputRoot -Profile $PackageProfile
}

$resolvedDistPath = Resolve-RepoPath -PathValue $DistPath
if (-not (Test-Path $resolvedDistPath)) {
    throw "PyInstaller dist folder not found: $resolvedDistPath"
}

$sourceExe = Resolve-PackagedExecutablePath -DistPath $resolvedDistPath
if (-not (Test-Path $sourceExe)) {
    throw "Expected packaged executable not found: $sourceExe"
}

$resolvedOutputRoot = Resolve-RepoPath -PathValue $OutputRoot
New-Item -ItemType Directory -Path $resolvedOutputRoot -Force | Out-Null

$runId = Get-Date -Format "yyyyMMdd_HHmmss"
$bundleRoot = Join-Path $resolvedOutputRoot $runId
$payloadRoot = Join-Path (Join-Path $bundleRoot "payload") $packageAppName
$scriptRoot = Join-Path $bundleRoot "scripts"

New-Item -ItemType Directory -Path $payloadRoot -Force | Out-Null
New-Item -ItemType Directory -Path $scriptRoot -Force | Out-Null

Copy-Item -Path (Join-Path $resolvedDistPath "*") -Destination $payloadRoot -Recurse -Force
Assert-CorexRuntimeBundlePayload -AppRoot $payloadRoot -Label "Installer payload"

$installScriptPath = Join-Path $scriptRoot "Install-COREX_Node_Editor.ps1"
$uninstallScriptPath = Join-Path $scriptRoot "Uninstall-COREX_Node_Editor.ps1"

$installScript = @'
[CmdletBinding()]
param(
    [string]$InstallRoot = "$env:LOCALAPPDATA\COREX_Node_Editor"
)

$ErrorActionPreference = "Stop"
$packageAppName = "COREX_Node_Editor"
$packageExeName = "COREX_Node_Editor.exe"
$packageRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$payload = Join-Path (Join-Path $packageRoot "payload") $packageAppName
if (-not (Test-Path $payload)) {
    throw "Installer payload not found: $payload"
}

$targetDir = Join-Path $InstallRoot $packageAppName
if (Test-Path $targetDir) {
    Remove-Item -Recurse -Force $targetDir
}
New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
Copy-Item -Path (Join-Path $payload "*") -Destination $targetDir -Recurse -Force

$record = [ordered]@{
    installed_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    install_root = $InstallRoot
    install_dir = $targetDir
    executable = (Join-Path $targetDir $packageExeName)
}
$recordPath = Join-Path $InstallRoot "install_record.json"
New-Item -ItemType Directory -Path $InstallRoot -Force | Out-Null
$record | ConvertTo-Json -Depth 5 | Set-Content -Path $recordPath
Write-Host "Installed to: $targetDir"
'@

$uninstallScript = @'
[CmdletBinding()]
param(
    [string]$InstallRoot = "$env:LOCALAPPDATA\COREX_Node_Editor"
)

$ErrorActionPreference = "Stop"
$packageAppName = "COREX_Node_Editor"
$targetDir = Join-Path $InstallRoot $packageAppName
if (Test-Path $targetDir) {
    Remove-Item -Recurse -Force $targetDir
}
$recordPath = Join-Path $InstallRoot "install_record.json"
if (Test-Path $recordPath) {
    Remove-Item -Force $recordPath
}
Write-Host "Uninstalled from: $targetDir"
'@

Set-Content -Path $installScriptPath -Value $installScript
Set-Content -Path $uninstallScriptPath -Value $uninstallScript

$bundleZip = Join-Path $bundleRoot "COREX_Node_Editor_installer_bundle_$runId.zip"
$zipCreated = $false
$zipError = ""
try {
    New-InstallerBundleZip -BundleRoot $bundleRoot -DestinationPath $bundleZip
    $zipCreated = $true
    $zipError = ""
}
catch {
    $zipError = $_.Exception.Message
}
if (-not $zipCreated) {
    Write-Warning "Installer zip creation skipped: $zipError"
}

$validationTempRoot = Join-Path $env:TEMP "ea_installer_validation_$runId"
if (Test-Path $validationTempRoot) {
    Remove-Item -Recurse -Force $validationTempRoot
}
New-Item -ItemType Directory -Path $validationTempRoot -Force | Out-Null

$packageRootForValidation = $bundleRoot
if ($zipCreated) {
    $expandedRoot = Join-Path $validationTempRoot "expanded"
    Expand-Archive -Path $bundleZip -DestinationPath $expandedRoot -Force
    $packageRootForValidation = $expandedRoot
}

$validationInstallRoot = Join-Path $validationTempRoot "install_root"
$expandedInstallScript = Join-Path $packageRootForValidation "scripts\Install-COREX_Node_Editor.ps1"
$expandedUninstallScript = Join-Path $packageRootForValidation "scripts\Uninstall-COREX_Node_Editor.ps1"
$validationShellPath = Resolve-PowerShellHostPath

try {
    Invoke-PowerShellScriptFile -HostPath $validationShellPath -ScriptPath $expandedInstallScript -InstallRoot $validationInstallRoot
}
catch {
    throw "Installer validation failed during install phase."
}

$installedExe = Join-Path (Join-Path $validationInstallRoot $packageAppName) $packageExeName
if (-not (Test-Path $installedExe)) {
    throw "Installer validation failed: installed executable not found at $installedExe"
}
Assert-CorexRuntimeBundlePayload -AppRoot (Join-Path $validationInstallRoot $packageAppName) -Label "Installed app"

$smokePassed = $false
$smokeExitCode = $null
try {
    $smokeExitCode = Invoke-PackagedStartupSmoke `
        -ExecutablePath $installedExe `
        -TimeoutSeconds $SmokeSeconds `
        -Label "Installer validation smoke test"
    $smokePassed = $true
}
catch {
    throw "Installer validation failed during smoke phase. $($_.Exception.Message)"
}

try {
    Invoke-PowerShellScriptFile -HostPath $validationShellPath -ScriptPath $expandedUninstallScript -InstallRoot $validationInstallRoot
}
catch {
    throw "Installer validation failed during uninstall phase."
}

$postUninstallExe = Join-Path (Join-Path $validationInstallRoot $packageAppName) $packageExeName
$uninstallPassed = -not (Test-Path $postUninstallExe)
if (-not $uninstallPassed) {
    throw "Installer validation failed: executable still exists after uninstall."
}

$sourceExeHash = (Get-FileHash -Path $sourceExe -Algorithm SHA256).Hash
$bundleHash = ""
if ($zipCreated -and (Test-Path $bundleZip)) {
    $bundleHash = (Get-FileHash -Path $bundleZip -Algorithm SHA256).Hash
}

$validationReport = [ordered]@{
    run_id = $runId
    package_profile = $PackageProfile
    generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    source_dist_path = $resolvedDistPath
    source_exe = $sourceExe
    source_exe_sha256 = $sourceExeHash
    installer_bundle = if ($zipCreated) { $bundleZip } else { "" }
    installer_bundle_sha256 = $bundleHash
    validation = [ordered]@{
        install_phase = "pass"
        smoke_phase = if ($smokePassed) { "pass" } else { "fail" }
        smoke_seconds = $SmokeSeconds
        smoke_exit_code = $smokeExitCode
        uninstall_phase = if ($uninstallPassed) { "pass" } else { "fail" }
        install_root = $validationInstallRoot
        validation_shell = $validationShellPath
    }
    packaging = [ordered]@{
        package_profile = $PackageProfile
        zip_created = $zipCreated
        zip_error = $zipError
        package_root = $bundleRoot
    }
}

$validationReportPath = Join-Path $bundleRoot "installer_validation.json"
$validationReport | ConvertTo-Json -Depth 10 | Set-Content -Path $validationReportPath

$manifest = [ordered]@{
    run_id = $runId
    package_profile = $PackageProfile
    generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    artifacts = [ordered]@{
        bundle_root = $bundleRoot
        installer_bundle = if ($zipCreated) { $bundleZip } else { "" }
        install_script = $installScriptPath
        uninstall_script = $uninstallScriptPath
        validation_report = $validationReportPath
    }
    checksums = [ordered]@{
        source_exe_sha256 = $sourceExeHash
        installer_bundle_sha256 = $bundleHash
    }
    packaging = [ordered]@{
        package_profile = $PackageProfile
        zip_created = $zipCreated
        zip_error = $zipError
    }
}

$manifestPath = Join-Path $bundleRoot "installer_manifest.json"
$manifest | ConvertTo-Json -Depth 10 | Set-Content -Path $manifestPath

try {
    Remove-Item -Recurse -Force $validationTempRoot
}
catch {
    # Non-fatal cleanup failure.
}

if ($zipCreated) {
    Write-Host "Installer bundle created: $bundleZip"
}
else {
    Write-Host "Installer bundle zip was not created; folder artifact retained: $bundleRoot"
}
Write-Host "Installer manifest: $manifestPath"
Write-Host "Installer validation: $validationReportPath"
Write-Host "Installer pipeline PASS."
