$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Push-Location $RepoRoot
try {
    python -B ver3\scripts\python\run_ver3_0_stepA_moneyness_refined_surface.py @args
}
finally {
    Pop-Location
}
