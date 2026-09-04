$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ver3Root = Split-Path -Parent $scriptDir
$projectRoot = Split-Path -Parent $ver3Root
Set-Location $projectRoot
python -B ver3\scripts\python\run_stepC_robustness_stability_diagnostics.py --strict @args
