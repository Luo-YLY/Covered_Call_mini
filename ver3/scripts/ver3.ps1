param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $Args
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..\..")
$Ver3Src = Join-Path $RepoRoot "ver3\src"

if ($env:PYTHONPATH) {
    $env:PYTHONPATH = "$RepoRoot;$Ver3Src;$env:PYTHONPATH"
} else {
    $env:PYTHONPATH = "$RepoRoot;$Ver3Src"
}

Push-Location $RepoRoot
try {
    python -m covered_call_mini_ver3.cli @Args
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
