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

$frontendRoot = Join-Path $projectRoot "src\website"
$frontendOutput = Join-Path $projectRoot "src\study_qb_assistant\api\static\site"
$frontendState = Join-Path $frontendOutput ".frontend-build-state"

function Ensure-FrontendDependencies {
    $nodeModules = Join-Path $frontendRoot "node_modules"
    $installedLock = Join-Path $nodeModules ".package-lock.json"
    $packageLock = Join-Path $frontendRoot "package-lock.json"
    $packageJson = Join-Path $frontendRoot "package.json"
    $needsInstall = -not (Test-Path -LiteralPath $nodeModules -PathType Container) -or
        -not (Test-Path -LiteralPath $installedLock -PathType Leaf)
    if (-not $needsInstall) {
        $installedAt = (Get-Item -LiteralPath $installedLock).LastWriteTimeUtc
        $needsInstall = (Get-Item -LiteralPath $packageLock).LastWriteTimeUtc -gt $installedAt -or
            (Get-Item -LiteralPath $packageJson).LastWriteTimeUtc -gt $installedAt
    }
    if (-not $needsInstall) {
        return
    }
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        throw "前端需要构建，但未找到 npm。请先安装 Node.js/npm。"
    }
    Write-Host "[frontend] installing dependencies with npm ci..."
    Push-Location $frontendRoot
    try {
        & npm ci --prefer-offline --no-audit --fund=false
        if ($LASTEXITCODE -ne 0) {
            throw "npm ci failed with exit code $LASTEXITCODE"
        }
    } finally {
        Pop-Location
    }
}

function Ensure-FrontendBuild {
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
        throw "前端构建检查需要 node。请先安装 Node.js。"
    }
    $fingerprintScript = Join-Path $projectRoot "scripts\frontend-fingerprint.mjs"
    $fingerprint = (& node $fingerprintScript).Trim()
    if (-not $fingerprint) {
        throw "无法计算前端构建指纹。"
    }
    $hasOutput = Test-Path -LiteralPath (Join-Path $frontendOutput "index.html") -PathType Leaf
    $previousFingerprint = if (Test-Path -LiteralPath $frontendState -PathType Leaf) {
        (Get-Content -LiteralPath $frontendState -Raw).Trim()
    } else {
        ""
    }
    if ($hasOutput -and $previousFingerprint -eq $fingerprint) {
        Write-Host "[frontend] build is up to date; skipped."
        return
    }

    Ensure-FrontendDependencies
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        throw "前端需要构建，但未找到 npm。请先安装 Node.js/npm。"
    }
    Write-Host "[frontend] changes detected; building..."
    Push-Location $frontendRoot
    try {
        & npm run build
        if ($LASTEXITCODE -ne 0) {
            throw "npm run build failed with exit code $LASTEXITCODE"
        }
    } finally {
        Pop-Location
    }
    if (-not (Test-Path -LiteralPath (Join-Path $frontendOutput "index.html") -PathType Leaf)) {
        throw "前端构建完成但未生成静态入口文件。"
    }
    Set-Content -LiteralPath $frontendState -Value $fingerprint -NoNewline -Encoding utf8
    Write-Host "[frontend] build completed."
}

Ensure-FrontendBuild

if ($Dev) {
    $env:STQB_RELOAD = "true"
    python -m study_qb_assistant.bootstrap
} else {
    $env:STQB_RELOAD = "false"
    python -m study_qb_assistant.bootstrap
}
