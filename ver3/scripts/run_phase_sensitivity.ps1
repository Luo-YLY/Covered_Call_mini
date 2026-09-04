param(
    [int]$MaxPhaseShift = 20,
    [int]$PhaseStep = 1,
    [switch]$SkipCycleAttribution,
    [switch]$SkipEnsemble,
    [switch]$SkipPlots,
    [switch]$Strict
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Ver3Root = Split-Path -Parent $ScriptDir
$ProjectRoot = Split-Path -Parent $Ver3Root

$argsList = @(
    "$ProjectRoot\ver3\scripts\python\run_phase_sensitivity_diagnostics.py",
    "--project-root", $ProjectRoot,
    "--ver3-root", "$ProjectRoot\ver3",
    "--max-phase-shift", $MaxPhaseShift,
    "--phase-step", $PhaseStep
)
if ($SkipCycleAttribution) { $argsList += "--skip-cycle-attribution" }
if ($SkipEnsemble) { $argsList += "--skip-ensemble" }
if ($SkipPlots) { $argsList += "--skip-plots" }
if ($Strict) { $argsList += "--strict" }

python @argsList
