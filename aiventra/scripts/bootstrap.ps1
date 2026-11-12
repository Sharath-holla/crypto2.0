$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) { uv venv --python 3.12 .venv }
& '.venv\Scripts\python.exe' scripts/configure.py
uv sync --extra dev --locked
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed' }
& '.venv\Scripts\python.exe' -m company_os.cli init
if ($LASTEXITCODE -ne 0) { throw 'Database initialization failed' }
Push-Location -LiteralPath apps/web
npm.cmd ci --no-fund
if ($LASTEXITCODE -ne 0) { throw 'Web dependency installation failed' }
Pop-Location
Write-Output 'Ready. Run scripts/start.ps1. Sign in with credentials in your private .env.'
