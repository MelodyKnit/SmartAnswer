param(
    [switch]$Dev,
    [string]$HostName = "127.0.0.1",
    [int]$Port = 8765
)

# 兼容 --dev 格式的参数，统一开发模式传参
if ($args -contains "--dev") {
    $Dev = $true
}

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Resolve-Path (Join-Path $scriptDir "..")
Set-Location $projectRoot
$reloadDir = Resolve-Path (Join-Path $projectRoot "src/study_qb_assistant")

$env:PYTHONPATH = Join-Path $projectRoot "src"
$env:STQB_HOST = $HostName
$env:STQB_PORT = [string]$Port

if ($Dev) {
    $env:STQB_RELOAD = "true"
    python -m uvicorn study_qb_assistant.bootstrap:create_runtime_app --factory --host $HostName --port $Port --reload --reload-dir "$reloadDir" --reload-include "*.py" --app-dir src
} else {
    $env:STQB_RELOAD = "false"
    python -m uvicorn study_qb_assistant.bootstrap:create_runtime_app --factory --host $HostName --port $Port --app-dir src
}
