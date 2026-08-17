param(
    [Parameter(Position = 0, Mandatory = $false, ValueFromRemainingArguments = $true)]
    [string[]]$ListenArgs,
    [switch]$Dev,
    [string]$HostName = "127.0.0.1",
    [int]$Port = 8765
)

# 统一解析位置参数与命名参数（支持 0.0.0.0:8080、0.0.0.0、8080 及 -Dev / --dev）
$allPositional = @($ListenArgs) + @($args)
if ($PSBoundParameters.ContainsKey('Dev') -and $PSBoundParameters['Dev']) {
    $Dev = $true
}
if ($allPositional -contains "--dev" -or $allPositional -contains "-Dev" -or $allPositional -contains "-dev") {
    $Dev = $true
}

$rawTarget = $allPositional | Where-Object { $_ -and -not $_.StartsWith("-") } | Select-Object -First 1

if ($rawTarget) {
    if ($rawTarget -match '^[0-9]+$') {
        $Port = [int]$rawTarget
    } elseif ($rawTarget -match '^(.+):([0-9]+)$') {
        $HostName = $Matches[1]
        $Port = [int]$Matches[2]
    } else {
        $HostName = $rawTarget
    }
}

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Resolve-Path (Join-Path $scriptDir "..")
Set-Location $projectRoot

$env:PYTHONPATH = Join-Path $projectRoot "src"
$env:STQB_HOST = $HostName
$env:STQB_PORT = [string]$Port

if ($Dev) {
    $env:STQB_RELOAD = "true"
    python -m study_qb_assistant.bootstrap
} else {
    $env:STQB_RELOAD = "false"
    python -m study_qb_assistant.bootstrap
}
