[CmdletBinding()]
param(
    [switch]$NoLaunch
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

$pythonExe = Join-Path $repoRoot "venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    throw "Virtualenv Python was not found at $pythonExe"
}

$guiScript = Join-Path $repoRoot "scripts\work_packet_gui.py"
if (-not (Test-Path $guiScript)) {
    throw "GUI launcher script was not found at $guiScript"
}

Write-Host "Repo root: $repoRoot"
Write-Host "Python:    $pythonExe"
Write-Host "GUI:       $guiScript"

if ($NoLaunch) {
    Write-Host "NoLaunch specified; exiting without starting the GUI."
    exit 0
}

& $pythonExe $guiScript
if ($LASTEXITCODE -ne 0) {
    throw "Work packet GUI exited with code $LASTEXITCODE."
}
