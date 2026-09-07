[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int] $Port = 8765
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

Push-Location $RepoRoot
try {
    Write-Host "Starting ETF covered-call dashboard: http://127.0.0.1:$Port/dashboard/"
    & python "scripts\serve_dashboard.py" --port $Port
    if ($LASTEXITCODE -ne 0) {
        throw "Dashboard server failed to start."
    }
}
finally {
    Pop-Location
}
