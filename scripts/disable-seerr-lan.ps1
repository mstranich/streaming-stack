[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$RuleName = 'Servarr-Seerr-LAN'
$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$EnvPath = Join-Path $RepositoryRoot '.env'

function Read-DotEnv {
    param([Parameter(Mandatory)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "No se encontró $Path."
    }
    $values = @{}
    foreach ($line in Get-Content -LiteralPath $Path) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith('#')) { continue }
        $separator = $trimmed.IndexOf('=')
        if ($separator -lt 1) { continue }
        $name = $trimmed.Substring(0, $separator).Trim()
        $value = $trimmed.Substring($separator + 1).Trim().Trim('"').Trim("'")
        $values[$name] = $value
    }
    return $values
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Ejecute este script desde PowerShell como administrador.'
}

$envFile = Read-DotEnv -Path $EnvPath
$listenAddress = $envFile['SEERR_LAN_LISTEN_ADDRESS']
$port = $envFile['SEERR_WEB_PORT']
if (-not $listenAddress -or -not $port) {
    throw 'Faltan SEERR_LAN_LISTEN_ADDRESS o SEERR_WEB_PORT en .env.'
}

$null = & netsh interface portproxy delete v4tov4 listenaddress=$listenAddress listenport=$port
if ($LASTEXITCODE -notin 0, 1) { throw 'No se pudo eliminar el portproxy.' }
Get-NetFirewallRule -Name $RuleName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
Write-Host 'Acceso LAN de Seerr deshabilitado; localhost continúa disponible.'
