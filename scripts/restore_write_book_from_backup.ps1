# Restore flat backup into novel_writer_write/library/books/default only
# Run: powershell -ExecutionPolicy Bypass -File scripts/restore_write_book_from_backup.ps1
# Optional: -BackupPath "D:\path\to\backup"

param(
    [string]$BackupPath = ""
)

$ErrorActionPreference = "Stop"

$DevRoot = Split-Path -Parent $PSScriptRoot
$Parent = Split-Path -Parent $DevRoot
$WriteRoot = Join-Path $Parent "novel_writer_write"

if (-not $BackupPath) {
    $BackupPath = Join-Path $Parent "novel_writer_data_backup_20260606"
}

if (-not (Test-Path $WriteRoot)) {
    Write-Host "[error] write copy not found: $WriteRoot"
    exit 1
}
if (-not (Test-Path $BackupPath)) {
    Write-Host "[error] backup not found: $BackupPath"
    exit 1
}

$BookDir = Join-Path $WriteRoot "library\books\default"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$safety = Join-Path $WriteRoot "library\books\default_before_restore_$stamp"

Write-Host "Restore backup into write copy (book: default)"
Write-Host "  backup: $BackupPath"
Write-Host "  target: $BookDir"
Write-Host ""
Write-Host "Current default book will move to:"
Write-Host "  $safety"
Write-Host ""
$confirm = Read-Host "Type yes to continue"
if ($confirm -ne "yes") {
    Write-Host "Cancelled."
    exit 0
}

if (Test-Path $BookDir) {
    Move-Item $BookDir $safety -Force
}
$null = New-Item -ItemType Directory -Path $BookDir -Force

robocopy $BackupPath $BookDir /E /NFL /NDL /NJH /NJS /NC /NS | Out-Null
if ($LASTEXITCODE -ge 8) {
    Write-Error "robocopy failed"
}

Write-Host ""
Write-Host "[done] Book restored in write copy."
Write-Host "Previous default at: $safety"

exit 0
