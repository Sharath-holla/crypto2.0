param(
    [Parameter(Mandatory = $true)][datetime]$HardStopAtUtc
)

$ErrorActionPreference = "Stop"
$project = "crypto-ai-trading-506300"
$zone = "asia-south1-a"
$instance = "crypto-phase7"
$log = Join-Path $PSScriptRoot "..\local_artifacts\phase7a-control-plane-watchdog.log"

while ([datetime]::UtcNow -lt $HardStopAtUtc.ToUniversalTime()) {
    $remaining = ($HardStopAtUtc.ToUniversalTime() - [datetime]::UtcNow).TotalSeconds
    Start-Sleep -Seconds ([math]::Max(1, [math]::Min(30, [int]$remaining)))
}

& gcloud compute instances stop $instance --zone $zone --project $project --quiet *>> $log
exit $LASTEXITCODE
