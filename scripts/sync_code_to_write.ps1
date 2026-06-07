# Sync code from novel_writer (dev) to novel_writer_write; never touch library/ or data/
# Run: powershell -ExecutionPolicy Bypass -File scripts/sync_code_to_write.ps1

$ErrorActionPreference = "Stop"

$DevRoot = Split-Path -Parent $PSScriptRoot
$Parent = Split-Path -Parent $DevRoot
$WriteRoot = Join-Path $Parent "novel_writer_write"

if (-not (Test-Path $WriteRoot)) {
    Write-Host "[error] write copy not found: $WriteRoot"
    Write-Host "Run scripts/init_write_copy.ps1 first."
    exit 1
}

Write-Host "Syncing code (library/ and data/ untouched)..."
Write-Host "  dev:   $DevRoot"
Write-Host "  write: $WriteRoot"

function Sync-Dir {
    param([string]$Relative)
    $src = Join-Path $DevRoot $Relative
    $dst = Join-Path $WriteRoot $Relative
    if (-not (Test-Path $src)) { return }
    $null = New-Item -ItemType Directory -Path $dst -Force -ErrorAction SilentlyContinue
    robocopy $src $dst /E /XD __pycache__ /XF *.pyc /NFL /NDL /NJH /NJS /NC /NS | Out-Null
    if ($LASTEXITCODE -ge 8) {
        throw "robocopy $Relative failed ($LASTEXITCODE)"
    }
}

foreach ($dir in @("web", "tests", "scripts", "docs")) {
    Sync-Dir $dir
}

$rootFiles = @(
    "requirements.txt", ".env.example", ".gitignore",
    "AGENTS.md", "README.md", "prices.json"
)
foreach ($py in Get-ChildItem -Path $DevRoot -Filter "*.py" -File) {
    $rootFiles += $py.Name
}
foreach ($bat in Get-ChildItem -Path $DevRoot -Filter "*.bat" -File) {
    if ($bat.Name -ne "启动web_开发.bat") {
        $rootFiles += $bat.Name
    }
}

foreach ($name in ($rootFiles | Select-Object -Unique)) {
    $src = Join-Path $DevRoot $name
    if (Test-Path $src) {
        Copy-Item $src (Join-Path $WriteRoot $name) -Force
    }
}

Write-Host ""
Write-Host "[done] Code synced to $WriteRoot"
Write-Host "Restart write-side web if it is running."

exit 0
