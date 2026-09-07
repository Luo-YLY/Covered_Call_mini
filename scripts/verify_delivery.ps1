[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $ScriptDir ".."))

Push-Location $RepoRoot
try {
    Write-Host "[verify] Checking Python and core dependencies"
    & python -c "import sys, numpy, pandas, scipy, matplotlib, yaml; print('Python ' + sys.version.split()[0] + ' / core dependencies available')"
    if ($LASTEXITCODE -ne 0) {
        throw "Core dependency check failed. Run: python -m pip install -r requirements.txt"
    }

    Write-Host "[verify] Running the full automated test suite"
    $env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
    & python -m pytest -q tests ver3\tests ver4\tests
    if ($LASTEXITCODE -ne 0) {
        throw "Automated tests failed."
    }

    if (Test-Path -LiteralPath (Join-Path $RepoRoot "RELEASE_README.md") -PathType Leaf) {
        Write-Host "[verify] Checking the final package frozen five-ETF boundary"
        & python scripts\verify_release_frozen_scope.py --root $RepoRoot
        if ($LASTEXITCODE -ne 0) {
            throw "Final package frozen data scope failed verification."
        }
    }
    else {
        Write-Host "[verify] Workspace mode: package-only frozen data check will run after extraction"
    }

    Write-Host "[verify] Checking delivery entrypoints"
    $requiredFiles = @(
        "dashboard\index.html",
        "dashboard\add-etf\index.html",
        "dashboard\portfolio\index.html",
        "ver3\dashboard\index.html",
        "ver4\dashboard\index.html",
        "scripts\serve_dashboard.py",
        "scripts\verify_release_frozen_scope.py",
        "scripts\package_project_release.ps1",
        "DELIVERY_CHECKLIST.md",
        "requirements.txt",
        "start_dashboard.ps1"
    )
    foreach ($relativePath in $requiredFiles) {
        if (-not (Test-Path -LiteralPath (Join-Path $RepoRoot $relativePath) -PathType Leaf)) {
            throw "Required delivery file is missing: $relativePath"
        }
    }

    Write-Host "[verify] PASS: dependencies, tests, and delivery entrypoints are ready."
}
finally {
    Pop-Location
}
