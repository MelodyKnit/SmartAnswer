param(
    [string]$HostName = "127.0.0.1",
    [int]$Port = 8765
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Resolve-Path (Join-Path $scriptDir "..")
Set-Location $projectRoot
$reloadDir = Resolve-Path (Join-Path $projectRoot "src/study_qb_assistant")

$env:PYTHONPATH = Join-Path $projectRoot "src"
$env:STQB_HOST = $HostName
$env:STQB_PORT = [string]$Port
$env:STQB_RELOAD = "true"

python -m uvicorn study_qb_assistant.runtime:create_runtime_app --factory --host $HostName --port $Port --reload --reload-dir "$reloadDir" --reload-include "*.py" --app-dir src
