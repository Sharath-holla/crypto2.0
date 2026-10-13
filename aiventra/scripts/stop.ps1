$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$processFile = Join-Path $projectRoot 'data/processes.json'
if (Test-Path -LiteralPath $processFile) {
  $processes = Get-Content -LiteralPath $processFile -Raw | ConvertFrom-Json
  foreach ($id in @($processes.api,$processes.worker,$processes.web)) {
    $running = Get-Process -Id $id -ErrorAction SilentlyContinue
    if ($running) {
      if ($processes.startedAt -and ([DateTimeOffset]$running.StartTime).ToUnixTimeSeconds() -lt ($processes.startedAt - 5)) { continue }
      $children = Get-CimInstance Win32_Process -Filter "ParentProcessId=$id" -ErrorAction SilentlyContinue
      foreach ($child in $children) {
        $grandchildren = Get-CimInstance Win32_Process -Filter "ParentProcessId=$($child.ProcessId)" -ErrorAction SilentlyContinue
        foreach ($grandchild in $grandchildren) { Stop-Process -Id $grandchild.ProcessId -ErrorAction SilentlyContinue }
        Stop-Process -Id $child.ProcessId -ErrorAction SilentlyContinue
      }
      Stop-Process -Id $id -ErrorAction SilentlyContinue
    }
  }
  Remove-Item -LiteralPath $processFile
}
Write-Output 'Managed processes stopped; database and artifacts preserved.'
