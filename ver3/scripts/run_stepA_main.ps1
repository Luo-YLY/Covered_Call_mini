$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Push-Location $RepoRoot
try {
    python -B ver3\scripts\python\run_ver3_0_stepA_single_etf_sleeves.py @args
}
finally {
    Pop-Location
}
