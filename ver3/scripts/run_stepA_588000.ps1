$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Push-Location $RepoRoot
try {
    python -B ver3\scripts\python\run_ver3_0_stepA_extension_588000_sleeve_clarification.py @args
}
finally {
    Pop-Location
}
