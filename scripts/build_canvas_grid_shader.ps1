[CmdletBinding()]
param([string]$Qsb = "qsb")

$ErrorActionPreference = "Stop"
$shader = Join-Path $PSScriptRoot "../ea_node_editor/ui_qml/components/graph_canvas/shaders/grid.frag"
# Package GLSL, HLSL, Metal and SPIR-V together; runtime needs no shader tools.
& $Qsb --qt6 --qsbversion 64 -o "$shader.qsb" $shader
if ($LASTEXITCODE -ne 0) { throw "Canvas grid shader compilation failed." }
