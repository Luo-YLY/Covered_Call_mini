$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ver3Root = Split-Path -Parent $scriptDir
$projectRoot = Split-Path -Parent $ver3Root
Set-Location $projectRoot
python -B ver3\scripts\python\run_stepB_plus_mdd_constrained_sharpe_frontier.py --strict @args
