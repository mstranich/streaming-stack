$ErrorActionPreference = "Stop"

Write-Host "== Compose container state and health =="
docker compose ps
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$services = @("transmission", "prowlarr", "sonarr", "radarr", "bazarr")
$failed = $false
foreach ($service in $services) {
    $id = docker compose ps -q $service
    if (-not $id) {
        Write-Error "$service has no container"
        $failed = $true
        continue
    }
    $state = docker inspect --format '{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' $id
    Write-Host "$service`t$state"
    if ($state -notmatch '^running\|healthy$') { $failed = $true }
}

Write-Host "`n== Internal APIs, DNS, storage and Jellyfin =="
docker compose --profile ops run --rm diagnose-stack
if ($LASTEXITCODE -ne 0) { $failed = $true }

if ($failed) {
    Write-Error "Diagnostic found one or more failures. No secrets were printed."
    exit 1
}
Write-Host "All checks passed."
