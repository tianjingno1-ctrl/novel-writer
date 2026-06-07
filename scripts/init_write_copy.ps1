# One-time: create sibling novel_writer_write from novel_writer (writing copy)
# Run from novel_writer root:
#   powershell -ExecutionPolicy Bypass -File scripts/init_write_copy.ps1

$ErrorActionPreference = "Stop"

$DevRoot = Split-Path -Parent $PSScriptRoot
$Parent = Split-Path -Parent $DevRoot
$WriteRoot = Join-Path $Parent "novel_writer_write"

if (Test-Path $WriteRoot) {
    Write-Host "[skip] already exists: $WriteRoot"
    Write-Host "Delete or rename it first to recreate."
    exit 1
}

Write-Host "Copying dev -> write ..."
Write-Host "  from: $DevRoot"
Write-Host "  to:   $WriteRoot"

$null = New-Item -ItemType Directory -Path $WriteRoot -Force

robocopy $DevRoot $WriteRoot /E `
    /XD __pycache__ .venv venv .git .cursor logs `
    /XF *.pyc debug-*.log `
    /NFL /NDL /NJH /NJS /NC /NS | Out-Null

if ($LASTEXITCODE -ge 8) {
    Write-Error "robocopy failed with exit code $LASTEXITCODE"
}

$envSrc = Join-Path $DevRoot ".env"
if (Test-Path $envSrc) {
    Copy-Item $envSrc (Join-Path $WriteRoot ".env") -Force
    Write-Host "Copied .env"
    $envPath = Join-Path $WriteRoot ".env"
    $envText = Get-Content $envPath -Raw -ErrorAction SilentlyContinue
    if ($envText -and $envText -notmatch 'NOVEL_RUNTIME_ENV') {
        Add-Content $envPath "`nNOVEL_RUNTIME_ENV=write"
        Write-Host "Set NOVEL_RUNTIME_ENV=write in write copy .env"
    }
}

Write-Host ""
Write-Host "[done] Write copy: $WriteRoot"
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. If dev E2E polluted chapters, restore backup:"
Write-Host "     powershell -File scripts/restore_write_book_from_backup.ps1"
Write-Host "  2. Daily writing: novel_writer_write, run web on port 8765"
Write-Host "  3. Dev/testing: novel_writer, run web dev on port 8766"
Write-Host "  4. After code changes: powershell -File scripts/sync_code_to_write.ps1"

exit 0
