$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $scriptRoot "..")
$hostRoot = Join-Path $repoRoot "web\excalidraw_host"
$assetRoot = Join-Path $repoRoot "ea_node_editor\web_assets\excalidraw_host"

Push-Location $hostRoot
try {
    npm ci
    npm run build
}
finally {
    Pop-Location
}

$remoteReferences = Get-ChildItem -Path $assetRoot -Recurse -File |
    Select-String -Pattern "https?://" -CaseSensitive:$false -List

if ($remoteReferences) {
    $paths = $remoteReferences | ForEach-Object { $_.Path } | Sort-Object -Unique
    throw "Excalidraw host bundle contains remote URL references: $($paths -join ', ')"
}
