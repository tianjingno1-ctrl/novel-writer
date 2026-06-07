# Ensure write copy uses NOVEL_RUNTIME_ENV=write (run once if write folder already exists)
$ErrorActionPreference = "Stop"
$DevRoot = Split-Path -Parent $PSScriptRoot
$WriteRoot = Join-Path (Split-Path -Parent $DevRoot) "novel_writer_write"
$envPath = Join-Path $WriteRoot ".env"
if (-not (Test-Path $envPath)) {
    Write-Host "[error] not found: $envPath"
    exit 1
}
$text = Get-Content $envPath -Raw
if ($text -match 'NOVEL_RUNTIME_ENV') {
    Write-Host "NOVEL_RUNTIME_ENV already set in write .env"
    exit 0
}
Add-Content $envPath "`nNOVEL_RUNTIME_ENV=write"
Write-Host "[done] Added NOVEL_RUNTIME_ENV=write to $envPath"
