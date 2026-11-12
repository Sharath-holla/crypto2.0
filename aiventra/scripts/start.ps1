$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
New-Item -ItemType Directory -Force -Path data | Out-Null
if (Get-NetTCPConnection -State Listen -LocalPort 8000,3000 -ErrorAction SilentlyContinue) { throw 'Port 8000 or 3000 is occupied. Stop the identified managed process first.' }
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
$apiProcess = Start-Process -FilePath $pythonExe -ArgumentList '-m','uvicorn','company_os.api:app','--host','127.0.0.1','--port','8000' -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput 'data/api.log' -RedirectStandardError 'data/api-error.log' -PassThru
$workerProcess = Start-Process -FilePath $pythonExe -ArgumentList '-m','company_os.workflows' -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput 'data/worker.log' -RedirectStandardError 'data/worker-error.log' -PassThru
$nodeExe = (Get-Command node.exe).Source
$nextScript = Join-Path $projectRoot 'apps/web/node_modules/next/dist/bin/next'
$webProcess = Start-Process -FilePath $nodeExe -ArgumentList ('"' + $nextScript + '"'),'dev','--hostname','127.0.0.1','--port','3000' -WorkingDirectory (Join-Path $projectRoot 'apps/web') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $projectRoot 'data/web.log') -RedirectStandardError (Join-Path $projectRoot 'data/web-error.log') -PassThru
@{api=$apiProcess.Id;worker=$workerProcess.Id;web=$webProcess.Id;startedAt=[DateTimeOffset]::Now.ToUnixTimeSeconds()} | ConvertTo-Json | Set-Content -LiteralPath 'data/processes.json'
Write-Output 'Starting http://localhost:3000. Logs: data/. Use scripts/stop.ps1 to stop these processes.'
