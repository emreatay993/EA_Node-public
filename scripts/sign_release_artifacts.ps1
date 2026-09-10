[CmdletBinding()]
param(
    [ValidateSet("base", "viewer", "web", "full")]
    [string]$PackageProfile = "base",
    [switch]$VerifyOnly,
    [switch]$RequireSignedArtifacts,
    [string]$CertThumbprint = "",
    [string]$TimestampServer = "",
    [string]$SigningOutputRoot = "",
    [string]$PackagedExePath = "",
    [string]$InstallerRoot = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

$packageAppName = "COREX_Node_Editor"
$packageExeName = "$packageAppName.exe"
$pyInstallerArtifactRoot = Join-Path $repoRoot "artifacts\pyinstaller"
$releaseArtifactRoot = Join-Path $repoRoot "artifacts\releases"

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
        [ValidateSet("base", "viewer", "web", "full")]
        [string]$Profile
    )
    return Join-Path (Resolve-PyInstallerDistPath -Profile $Profile) $packageExeName
}

function Resolve-SigningOutputRoot {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("base", "viewer", "web", "full")]
        [string]$Profile
    )
    return Join-Path (Join-Path $releaseArtifactRoot "signing") $Profile
}

function Resolve-InstallerRoot {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("base", "viewer", "web", "full")]
        [string]$Profile
    )
    return Join-Path (Join-Path $releaseArtifactRoot "installer") $Profile
}

if ([string]::IsNullOrWhiteSpace($SigningOutputRoot)) {
    $SigningOutputRoot = Resolve-SigningOutputRoot -Profile $PackageProfile
}
if ([string]::IsNullOrWhiteSpace($PackagedExePath)) {
    $PackagedExePath = Resolve-PackagedExecutablePath -Profile $PackageProfile
}
if ([string]::IsNullOrWhiteSpace($InstallerRoot)) {
    $InstallerRoot = Resolve-InstallerRoot -Profile $PackageProfile
}

function Get-LatestInstallerRun {
    param(
        [Parameter(Mandatory = $true)]
        [string]$InstallerRootPath
    )
    if (-not (Test-Path $InstallerRootPath)) {
        return $null
    }
    return Get-ChildItem -Path $InstallerRootPath -Directory |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
}

function Get-SignatureSnapshot {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath
    )

    if (-not (Test-Path $FilePath)) {
        return [ordered]@{
            exists = $false
            signature_status = "missing"
            status_message = "File not found."
            signer_subject = ""
            signer_thumbprint = ""
            timestamp_subject = ""
            timestamp_thumbprint = ""
        }
    }

    try {
        $signature = Get-AuthenticodeSignature -FilePath $FilePath
        $signer = $signature.SignerCertificate
        $timestamp = $signature.TimeStamperCertificate
        return [ordered]@{
            exists = $true
            signature_status = [string]$signature.Status
            status_message = [string]$signature.StatusMessage
            signer_subject = if ($null -ne $signer) { [string]$signer.Subject } else { "" }
            signer_thumbprint = if ($null -ne $signer) { [string]$signer.Thumbprint } else { "" }
            timestamp_subject = if ($null -ne $timestamp) { [string]$timestamp.Subject } else { "" }
            timestamp_thumbprint = if ($null -ne $timestamp) { [string]$timestamp.Thumbprint } else { "" }
        }
    }
    catch {
        return [ordered]@{
            exists = $true
            signature_status = "error"
            status_message = [string]$_.Exception.Message
            signer_subject = ""
            signer_thumbprint = ""
            timestamp_subject = ""
            timestamp_thumbprint = ""
        }
    }
}

function Is-SignatureValid {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Status
    )
    return $Status -eq "Valid"
}

function Is-SignablePath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath
    )
    $ext = [System.IO.Path]::GetExtension($FilePath).ToLowerInvariant()
    return @(".exe", ".msi", ".ps1", ".dll", ".sys", ".cat", ".ocx") -contains $ext
}

function Resolve-Certificate {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Thumbprint
    )
    $normalized = ($Thumbprint -replace "\s", "").ToUpperInvariant()
    $candidatePaths = @(
        "Cert:\CurrentUser\My\$normalized",
        "Cert:\LocalMachine\My\$normalized"
    )
    foreach ($path in $candidatePaths) {
        if (Test-Path $path) {
            return Get-Item -Path $path
        }
    }
    throw "Certificate not found for thumbprint $normalized in CurrentUser\My or LocalMachine\My."
}

function Invoke-Signing {
    param(
        [Parameter(Mandatory = $true)]
        [array]$Targets,
        [Parameter(Mandatory = $true)]
        [object]$Certificate,
        [string]$TimestampServerUrl
    )
    foreach ($target in $Targets) {
        if (-not $target.exists) {
            throw "Signing target missing: $($target.path)"
        }
        if (-not $target.signable) {
            continue
        }
        $setSignatureParams = @{
            FilePath = $target.path
            Certificate = $Certificate
            HashAlgorithm = "SHA256"
        }
        if ($TimestampServerUrl) {
            $setSignatureParams["TimestampServer"] = $TimestampServerUrl
        }
        $signatureResult = Set-AuthenticodeSignature @setSignatureParams
        if ($signatureResult.Status -ne "Valid") {
            throw "Signing failed for $($target.path). Status=$($signatureResult.Status) Message=$($signatureResult.StatusMessage)"
        }
    }
}

$resolvedSigningOutputRoot = Resolve-RepoPath -PathValue $SigningOutputRoot
New-Item -ItemType Directory -Path $resolvedSigningOutputRoot -Force | Out-Null

$resolvedPackagedExePath = Resolve-RepoPath -PathValue $PackagedExePath
$resolvedInstallerRoot = Resolve-RepoPath -PathValue $InstallerRoot
$latestInstallerRun = Get-LatestInstallerRun -InstallerRootPath $resolvedInstallerRoot

$targetFiles = New-Object System.Collections.ArrayList
[void]$targetFiles.Add($resolvedPackagedExePath)
if ($null -ne $latestInstallerRun) {
    $installerRunPath = $latestInstallerRun.FullName
    $installerBundle = Join-Path $installerRunPath ("COREX_Node_Editor_installer_bundle_" + $latestInstallerRun.Name + ".zip")
    $installerScript = Join-Path $installerRunPath "scripts\Install-COREX_Node_Editor.ps1"
    $uninstallScript = Join-Path $installerRunPath "scripts\Uninstall-COREX_Node_Editor.ps1"
    [void]$targetFiles.Add($installerBundle)
    [void]$targetFiles.Add($installerScript)
    [void]$targetFiles.Add($uninstallScript)
}

if (-not $CertThumbprint) {
    $CertThumbprint = [string]$env:EA_SIGN_CERT_THUMBPRINT
}
if (-not $TimestampServer) {
    $TimestampServer = [string]$env:EA_SIGN_TIMESTAMP_URL
}

if (-not $PSBoundParameters.ContainsKey("RequireSignedArtifacts")) {
    $envRequireSigned = [string]$env:EA_SIGN_REQUIRE_SIGNED
    $RequireSignedArtifacts = $envRequireSigned -in @("1", "true", "TRUE", "yes", "YES")
}

$targets = @()
foreach ($filePath in $targetFiles) {
    $snapshot = Get-SignatureSnapshot -FilePath $filePath
    $targets += [ordered]@{
        path = $filePath
        relative_path = $filePath.Replace([string]$repoRoot, "").TrimStart("\")
        signable = Is-SignablePath -FilePath $filePath
        exists = $snapshot.exists
        signature_status = $snapshot.signature_status
        status_message = $snapshot.status_message
        signer_subject = $snapshot.signer_subject
        signer_thumbprint = $snapshot.signer_thumbprint
        timestamp_subject = $snapshot.timestamp_subject
        timestamp_thumbprint = $snapshot.timestamp_thumbprint
    }
}

$runId = Get-Date -Format "yyyyMMdd_HHmmss"
$runDir = Join-Path $resolvedSigningOutputRoot $runId
New-Item -ItemType Directory -Path $runDir -Force | Out-Null

if (-not $VerifyOnly) {
    if (-not $CertThumbprint) {
        throw "Signing mode requires CertThumbprint argument or EA_SIGN_CERT_THUMBPRINT environment variable."
    }
    $certificate = Resolve-Certificate -Thumbprint $CertThumbprint
    Invoke-Signing -Targets $targets -Certificate $certificate -TimestampServerUrl $TimestampServer
    $refreshedTargets = @()
    foreach ($target in $targets) {
        $snapshot = Get-SignatureSnapshot -FilePath $target.path
        $refreshedTargets += [ordered]@{
            path = $target.path
            relative_path = $target.relative_path
            signable = $target.signable
            exists = $snapshot.exists
            signature_status = $snapshot.signature_status
            status_message = $snapshot.status_message
            signer_subject = $snapshot.signer_subject
            signer_thumbprint = $snapshot.signer_thumbprint
            timestamp_subject = $snapshot.timestamp_subject
            timestamp_thumbprint = $snapshot.timestamp_thumbprint
        }
    }
    $targets = $refreshedTargets
}

$verificationFailures = @()
foreach ($target in $targets) {
    if (-not $target.exists) {
        $verificationFailures += "Missing artifact: $($target.relative_path)"
        continue
    }
    if (-not $target.signable) {
        continue
    }
    if ($RequireSignedArtifacts -and -not (Is-SignatureValid -Status $target.signature_status)) {
        $verificationFailures += "Invalid signature status for $($target.relative_path): $($target.signature_status)"
    }
}

$manifest = [ordered]@{
    run_id = $runId
    generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    package_profile = $PackageProfile
    mode = if ($VerifyOnly) { "verify_only" } else { "sign_and_verify" }
    require_signed_artifacts = [bool]$RequireSignedArtifacts
    certificate_thumbprint = $CertThumbprint
    timestamp_server = $TimestampServer
    installer_run_id = if ($null -ne $latestInstallerRun) { $latestInstallerRun.Name } else { "" }
    targets = $targets
    verification_failures = $verificationFailures
}

$manifestPath = Join-Path $runDir "signing_manifest.json"
$manifest | ConvertTo-Json -Depth 12 | Set-Content -Path $manifestPath

$summaryCertThumbprint = if ([string]::IsNullOrWhiteSpace([string]$CertThumbprint)) { "n/a" } else { [string]$CertThumbprint }
$summaryTimestampServer = if ([string]::IsNullOrWhiteSpace([string]$TimestampServer)) { "n/a" } else { [string]$TimestampServer }
$summaryInstallerRunId = if ([string]::IsNullOrWhiteSpace([string]$manifest.installer_run_id)) { "n/a" } else { [string]$manifest.installer_run_id }

$summaryLines = New-Object System.Collections.ArrayList
[void]$summaryLines.Add("# Signing Verification Summary")
[void]$summaryLines.Add("")
[void]$summaryLines.Add("- Run id: " + $runId)
[void]$summaryLines.Add("- Package profile: " + $PackageProfile)
[void]$summaryLines.Add("- Mode: " + $manifest.mode)
[void]$summaryLines.Add("- Require signed artifacts: " + $manifest.require_signed_artifacts)
[void]$summaryLines.Add("- Certificate thumbprint: " + $summaryCertThumbprint)
[void]$summaryLines.Add("- Timestamp server: " + $summaryTimestampServer)
[void]$summaryLines.Add("- Installer run id: " + $summaryInstallerRunId)
[void]$summaryLines.Add("")
[void]$summaryLines.Add("| Target | Exists | Signable | Status | Signer Thumbprint | Timestamp Thumbprint |")
[void]$summaryLines.Add("|---|---|---|---|---|---|")
foreach ($target in $targets) {
    $rowSignerThumbprint = if ([string]::IsNullOrWhiteSpace([string]$target.signer_thumbprint)) { "" } else { [string]$target.signer_thumbprint }
    $rowTimestampThumbprint = if ([string]::IsNullOrWhiteSpace([string]$target.timestamp_thumbprint)) { "" } else { [string]$target.timestamp_thumbprint }
    $rowLine = "| {0} | {1} | {2} | {3} | {4} | {5} |" -f $target.relative_path, $target.exists, $target.signable, $target.signature_status, $rowSignerThumbprint, $rowTimestampThumbprint
    [void]$summaryLines.Add($rowLine)
}
if ($verificationFailures.Count -gt 0) {
    [void]$summaryLines.Add("")
    [void]$summaryLines.Add("## Failures")
    [void]$summaryLines.Add("")
    foreach ($failure in $verificationFailures) {
        [void]$summaryLines.Add("- $failure")
    }
}

$summaryPath = Join-Path $runDir "signing_summary.md"
$summaryLines -join "`n" | Set-Content -Path $summaryPath

Write-Host "Signing manifest: $manifestPath"
Write-Host "Signing summary:  $summaryPath"
if ($verificationFailures.Count -gt 0) {
    Write-Warning ("Signing verification failures: " + ($verificationFailures -join "; "))
    throw "Signing verification failed."
}
Write-Host "Signing verification PASS."
