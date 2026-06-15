# 开发环境一键启动（API + 前端），输出写入 logs/dev/
$ErrorActionPreference = 'Continue'
$Root = Split-Path $PSScriptRoot -Parent
$LogDir = Join-Path $Root 'logs\dev'
$FrontendDir = Join-Path $Root 'frontend'
$ApiPort = if ($env:NOVEL_WEB_PORT) { [int]$env:NOVEL_WEB_PORT } else { 8765 }
$FePort = 5173

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-SessionLog([string]$Message) {
    $line = "[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
    Add-Content -Path (Join-Path $LogDir 'session.log') -Value $line -Encoding UTF8
    Write-Host $line
}

function Stop-PortListener([int]$Port) {
    $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
        $proc = Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue
        if (-not $proc) { continue }
        Write-SessionLog "stop port $Port pid=$($proc.Id) name=$($proc.ProcessName)"
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    }
}

function Test-HttpOk([string]$Url) {
    try {
        $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 8
        return "OK $($r.StatusCode)"
    } catch {
        return "FAIL $($_.Exception.Message)"
    }
}

function Wait-HttpOk([string]$Url, [int]$TimeoutSec = 60, [int]$IntervalSec = 2) {
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        $status = Test-HttpOk $Url
        if ($status -like 'OK*') { return $status }
        Start-Sleep -Seconds $IntervalSec
    }
    return Test-HttpOk $Url
}

Write-SessionLog '=== dev-with-logs start ==='
Write-SessionLog "root=$Root apiPort=$ApiPort fePort=$FePort"

if (-not (Test-Path (Join-Path $Root '.env'))) {
    Write-SessionLog 'ERROR missing .env — copy .env.example and add API keys'
    exit 1
}

if (-not (Test-Path (Join-Path $FrontendDir 'node_modules'))) {
    Write-SessionLog 'npm install (first run)...'
    Push-Location $FrontendDir
    npm install *>&1 | Tee-Object -FilePath (Join-Path $LogDir 'npm-install.log')
    Pop-Location
}

Stop-PortListener $ApiPort
foreach ($p in $FePort..($FePort + 3)) { Stop-PortListener $p }

$apiOut = Join-Path $LogDir 'api-out.log'
$apiErr = Join-Path $LogDir 'api-err.log'
$feLog = Join-Path $LogDir 'frontend.log'

Set-Content -Path $apiOut -Value '' -Encoding UTF8
Set-Content -Path $apiErr -Value '' -Encoding UTF8
try {
    Add-Content -Path $feLog -Value "`n--- $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') dev-with-logs ---" -Encoding UTF8
} catch {
    $feLog = Join-Path $LogDir ("frontend-{0}.log" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
    Write-SessionLog "frontend.log locked, using $feLog"
}

$env:NOVEL_WEB_NO_BROWSER = '1'
Start-Process -FilePath 'python' -ArgumentList 'web_app.py' -WorkingDirectory $Root `
    -RedirectStandardOutput $apiOut -RedirectStandardError $apiErr -WindowStyle Hidden
Write-SessionLog "api started -> logs/dev/api-out.log + api-err.log"

Start-Process -FilePath 'cmd.exe' -ArgumentList "/c npm run dev 1>> `"$feLog`" 2>>&1" `
    -WorkingDirectory $FrontendDir -WindowStyle Hidden
Write-SessionLog "frontend started -> logs/dev/frontend.log"

$apiStatus = Wait-HttpOk "http://127.0.0.1:$ApiPort/api/status" -TimeoutSec 45
$feStatus = Wait-HttpOk "http://127.0.0.1:$FePort/" -TimeoutSec 90
Write-SessionLog "probe api/status -> $apiStatus"
Write-SessionLog "probe frontend -> $feStatus"

if ($feStatus -like 'OK*') {
    Write-SessionLog "OPEN http://127.0.0.1:$FePort/"
    Write-SessionLog "API docs http://127.0.0.1:$ApiPort/docs"
    try { Start-Process "http://127.0.0.1:$FePort/" } catch { Write-SessionLog 'browser open skipped' }
} else {
    Write-SessionLog 'frontend not ready — check logs/dev/frontend.log and api-err.log'
    exit 1
}

Write-SessionLog '=== dev-with-logs ready (Ctrl+C in child windows not needed; stop via Task Manager or re-run script) ==='
