param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $Args
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..\..")

Push-Location $RepoRoot
try {
    python ver3\scripts\python\run_effective_delta_equivalence_diagnostic.py @Args
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
