$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Push-Location $RepoRoot
try {
    python -B ver3\scripts\python\ver3_0_stepB_fixed_weight_universe_comparison.py @args
}
finally {
    Pop-Location
}
