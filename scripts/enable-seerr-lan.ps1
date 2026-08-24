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

function Require-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Ejecute este script desde PowerShell como administrador.'
    }
}

Require-Administrator
$envFile = Read-DotEnv -Path $EnvPath
$listenAddress = $envFile['SEERR_LAN_LISTEN_ADDRESS']
$portText = $envFile['SEERR_WEB_PORT']
$allowedText = $envFile['SEERR_LAN_ALLOWED_REMOTES']
$hostnamesText = $envFile['SEERR_LAN_HOSTNAMES']

$parsedAddress = $null
if (-not [Net.IPAddress]::TryParse($listenAddress, [ref]$parsedAddress) -or
    $parsedAddress.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork -or
    $listenAddress -eq '0.0.0.0') {
    throw 'SEERR_LAN_LISTEN_ADDRESS debe ser una dirección IPv4 concreta, no 0.0.0.0.'
}
$port = 0
if (-not [int]::TryParse($portText, [ref]$port) -or $port -lt 1 -or $port -gt 65535) {
    throw 'SEERR_WEB_PORT debe ser un puerto válido.'
}
if (-not (Get-NetIPAddress -AddressFamily IPv4 -IPAddress $listenAddress -ErrorAction SilentlyContinue)) {
    throw "La dirección $listenAddress no pertenece actualmente a este equipo."
}
$allowedRemotes = @($allowedText -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
if ($allowedRemotes.Count -eq 0) {
    throw 'SEERR_LAN_ALLOWED_REMOTES no puede estar vacío.'
}

if ((Get-NetConnectionProfile | Where-Object IPv4Connectivity -ne 'Disconnected').NetworkCategory -contains 'Public') {
    Write-Warning 'Hay una interfaz activa con perfil Public; la regla sólo se aplicará al perfil Private.'
}

$null = & netsh interface portproxy delete v4tov4 listenaddress=$listenAddress listenport=$port
if ($LASTEXITCODE -notin 0, 1) { throw 'No se pudo limpiar el portproxy anterior.' }
$output = & netsh interface portproxy add v4tov4 listenaddress=$listenAddress listenport=$port connectaddress=127.0.0.1 connectport=$port
if ($LASTEXITCODE -ne 0) { throw "No se pudo crear el portproxy: $output" }

Get-NetFirewallRule -Name $RuleName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule `
    -Name $RuleName `
    -DisplayName 'Servarr - Seerr LAN' `
    -Description 'Permite Seerr sólo desde las direcciones definidas en .env.' `
    -Enabled True `
    -Profile Private `
    -Direction Inbound `
    -Action Allow `
    -Protocol TCP `
    -LocalAddress $listenAddress `
    -LocalPort $port `
    -RemoteAddress $allowedRemotes `
    -EdgeTraversalPolicy Block | Out-Null

Write-Host "Seerr habilitado para $allowedText en http://${listenAddress}:$port/"
foreach ($hostname in @($hostnamesText -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })) {
    Write-Host "Alias esperado: http://${hostname}:$port/ (depende de DNS/LLMNR/archivo hosts del cliente)."
}
