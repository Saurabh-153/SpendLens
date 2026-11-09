# Starts the SpendLens API. Reads DATABASE_URL from .env.local (git-ignored) when it exists,
# so the app runs on PostgreSQL; without it the app uses the SQLite file as before.
$root = $PSScriptRoot
$envFile = Join-Path $root '.env.local'
if (Test-Path $envFile) {
    foreach ($line in Get-Content $envFile) {
        if ($line -match '^\s*DATABASE_URL\s*=\s*(.+?)\s*$') { $env:DATABASE_URL = $Matches[1] }
    }
}
if ($env:DATABASE_URL) { Write-Host "Database: $($env:DATABASE_URL -replace '://([^:]+):[^@]+@', '://$1:***@')" }
else { Write-Host 'Database: SQLite (spendlens/spendlens_v2.db)' }
Set-Location (Join-Path $root 'spendlens')
& (Join-Path $root 'venv_expense\Scripts\python.exe') app.py
