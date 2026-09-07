[CmdletBinding()]
param(
    [ValidateSet("All", "Source", "Demo", "Inputs", "Final")]
    [string] $Profile = "Final",
    [string] $ReleaseTag = (Get-Date -Format "yyyyMMdd_HHmmss"),
    [string] $OutputRoot
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $ScriptDir ".."))
if (-not $OutputRoot) {
    $OutputRoot = Join-Path $RepoRoot "dist"
}
elseif (-not [System.IO.Path]::IsPathRooted($OutputRoot)) {
    $OutputRoot = Join-Path $RepoRoot $OutputRoot
}
$OutputRoot = [System.IO.Path]::GetFullPath($OutputRoot)

if ($OutputRoot -eq $RepoRoot) {
    throw "OutputRoot must not be the repository root."
}

$SkippedDirectoryPattern = '^(?:\.git|\.runtime|\.tmp|\.pytest_cache|\.mypy_cache|\.ruff_cache|\.venv|\.vscode|__pycache__|build|dist|env|htmlcov|temp|tmp.*|venv|soffice_.*|render_tmp)$'
$SkippedFilePattern = '(?i)(?:\.py[co]|\.tmp|\.bak|\.inspect\.ndjson|\.DS_Store)$|^~\$'
$ForbiddenReleaseNamePattern = '(?i)(?:^|[._-])(?:token|secret|password|credential)(?:[._-]|$)|^\.env(?:\..*)?$'
$InputRelativeFiles = @(
    "data\raw\etf_metadata.csv",
    "data\raw\etf_prices.csv",
    "data\raw\options.csv",
    "data\raw\options_daily.csv",
    "data\source\delta_enriched_options.csv",
    "data\frozen_inputs\ver3_0_510050\ver2_1_daily_mtm.csv",
    "data\frozen_inputs\ver3_0_510050\ver2_1_periods_with_regime.csv",
    "outputs\ver3_0_stepA_moneyness_refined_daily_mtm_surface\summary\ver3_0_stepA_moneyness_refined_daily_mtm_surface_grid.csv",
    "outputs\ver3_0_stepA_moneyness_refined_daily_mtm_surface\daily\ver3_0_stepA_moneyness_refined_daily_mtm_daily_paths.csv"
)
$RawDataCatalogRelativeFiles = @($InputRelativeFiles) + @(
    "outputs\ver3_1_effective_zone_target_delta\portfolio\ver3_1_fixed_weight_daily_returns.csv",
    "outputs\ver3_1_effective_zone_target_delta\portfolio\ver3_1_fixed_weight_summary.csv",
    "outputs\ver3_1_effective_zone_target_delta\portfolio\ver3_1_mdd_frontier_grid.csv",
    "outputs\ver3_1_effective_zone_target_delta\portfolio\ver3_1_mdd_frontier_best_by_dstar.csv",
    "outputs\ver4_1_delta_buyback\ver4_1_delta_buyback_cycle_ledger.csv",
    "outputs\ver4_1_delta_buyback\ver4_1_delta_buyback_cycle_daily_mtm.csv",
    "outputs\ver4_1_delta_buyback\ver4_1_delta_buyback_summary.csv",
    "outputs\ver4_2_tp80_buyback\ver4_2_tp80_buyback_cycle_ledger.csv",
    "outputs\ver4_2_tp80_buyback\ver4_2_tp80_buyback_cycle_daily_mtm.csv",
    "outputs\ver4_2_tp80_buyback\ver4_2_tp80_buyback_summary.csv"
)
foreach ($etfCode in @("510050", "510300", "510500", "159915", "588000")) {
    $RawDataCatalogRelativeFiles += @(
        "outputs\ver4_0_single_etf_cycle_cashflow\$etfCode\period\ver4_0_cycle_ledger.csv",
        "outputs\ver4_0_single_etf_cycle_cashflow\$etfCode\daily_mtm\ver4_0_cycle_daily_mtm.csv",
        "outputs\ver4_0_single_etf_cycle_cashflow\$etfCode\summary\ver4_0_cycle_cashflow_summary.csv"
    )
}

function Write-Step {
    param([string] $Message)
    Write-Host "[project-release] $Message"
}

function Get-RelativePathCompat {
    param(
        [string] $BasePath,
        [string] $TargetPath
    )

    $baseFull = [System.IO.Path]::GetFullPath($BasePath).TrimEnd('\', '/')
    $targetFull = [System.IO.Path]::GetFullPath($TargetPath)
    if ($targetFull.Equals($baseFull, [System.StringComparison]::OrdinalIgnoreCase)) {
        return "."
    }

    $prefix = $baseFull + [System.IO.Path]::DirectorySeparatorChar
    if (-not $targetFull.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Target path is outside the expected base path: $targetFull"
    }
    return $targetFull.Substring($prefix.Length)
}

function Test-SkippedFile {
    param([System.IO.FileInfo] $File, [string] $SourceBase)

    $relative = Get-RelativePathCompat -BasePath $SourceBase -TargetPath $File.FullName
    $segments = $relative -split '[\\/]'
    foreach ($segment in $segments[0..([Math]::Max(0, $segments.Count - 2))]) {
        if ($segment -match $SkippedDirectoryPattern) {
            return $true
        }
    }
    if ($File.Name -match $SkippedFilePattern) {
        return $true
    }
    if ($File.Name -match $ForbiddenReleaseNamePattern) {
        return $true
    }
    return $false
}

function Copy-FileRelative {
    param(
        [string] $RelativePath,
        [string] $PackageRoot,
        [switch] $Optional
    )

    $source = Join-Path $RepoRoot $RelativePath
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        if ($Optional) {
            return
        }
        throw "Required file is missing: $RelativePath"
    }
    $sourceItem = Get-Item -LiteralPath $source
    if (Test-SkippedFile -File $sourceItem -SourceBase $RepoRoot) {
        throw "Refusing to copy excluded file: $RelativePath"
    }
    $destination = Join-Path $PackageRoot $RelativePath
    New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
    Copy-Item -LiteralPath $source -Destination $destination -Force
}

function Copy-TreeRelative {
    param(
        [string] $RelativePath,
        [string] $PackageRoot,
        [switch] $Optional
    )

    $source = Join-Path $RepoRoot $RelativePath
    if (-not (Test-Path -LiteralPath $source -PathType Container)) {
        if ($Optional) {
            return
        }
        throw "Required directory is missing: $RelativePath"
    }

    $files = Get-ChildItem -LiteralPath $source -Recurse -File -Force -ErrorAction SilentlyContinue
    foreach ($file in $files) {
        if (Test-SkippedFile -File $file -SourceBase $source) {
            continue
        }
        $withinTree = Get-RelativePathCompat -BasePath $source -TargetPath $file.FullName
        $destination = Join-Path (Join-Path $PackageRoot $RelativePath) $withinTree
        New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
        Copy-Item -LiteralPath $file.FullName -Destination $destination -Force
    }
}

function Copy-InputFiles {
    param([string] $PackageRoot)

    foreach ($file in $InputRelativeFiles) {
        Copy-FileRelative -RelativePath $file -PackageRoot $PackageRoot
    }
}

function Get-GitSnapshot {
    $head = (& git -C $RepoRoot rev-parse HEAD 2>$null)
    $branch = (& git -C $RepoRoot branch --show-current 2>$null)
    $status = (& git -C $RepoRoot status --short --branch 2>$null)
    return @(
        "generated_at=$(Get-Date -Format o)",
        "branch=$branch",
        "head=$head",
        "working_tree_clean=$([bool](-not ($status | Select-Object -Skip 1)))",
        "",
        "git status --short --branch",
        ($status -join [Environment]::NewLine)
    ) -join [Environment]::NewLine
}

function Write-ReleaseMetadata {
    param(
        [string] $PackageRoot,
        [string] $PackageProfile
    )

    $scopeText = switch ($PackageProfile) {
        "source" { "Source code, tests, non-secret configuration, and documentation; raw market data and generated results are excluded." }
        "demo" { "Source package content plus the unified dashboard, selected reports, presentation material, and dashboard dependencies." }
        "inputs" { "Frozen ETF and option inputs required by the research mainline; credentials and machine-specific endpoint configuration are excluded." }
        "final" { "Complete final package with source, tests, unified dashboard, selected research evidence, and frozen runtime inputs." }
    }

    $readme = @"
# covered_call_mini $PackageProfile release

Generated at: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss zzz")

## Scope

$scopeText

## Research boundary

- This package was generated from the current workspace snapshot. See GIT_SNAPSHOT.txt for commit and cleanliness evidence.
- The package excludes config/*.txt, .env, access tokens, passwords, and machine-specific endpoint configuration.
- The final package is the preferred complete delivery. Source, demo, and inputs remain available only for split delivery when needed.
- All research outputs are research-only and are not trading instructions.

## Unified dashboard

From the extracted demo or final package, run:

    python scripts\serve_dashboard.py --port 8765

Then open:

- `http://127.0.0.1:8765/dashboard/`

## Integrity

FILE_INDEX.csv records each package file path, byte size, and SHA-256. The ZIP hash is stored in the adjacent .sha256 file.
"@
    Set-Content -LiteralPath (Join-Path $PackageRoot "RELEASE_README.md") -Value $readme -Encoding UTF8
    Set-Content -LiteralPath (Join-Path $PackageRoot "GIT_SNAPSHOT.txt") -Value (Get-GitSnapshot) -Encoding UTF8

    $files = Get-ChildItem -LiteralPath $PackageRoot -Recurse -File -Force | Sort-Object FullName
    $indexRows = foreach ($file in $files) {
        [pscustomobject]@{
            path = (Get-RelativePathCompat -BasePath $PackageRoot -TargetPath $file.FullName).Replace('\', '/')
            bytes = $file.Length
            sha256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    }
    $indexRows | Export-Csv -LiteralPath (Join-Path $PackageRoot "FILE_INDEX.csv") -NoTypeInformation -Encoding UTF8
}

function Assert-ReleaseSafety {
    param(
        [string] $PackageRoot,
        [string] $PackageProfile
    )

    $forbidden = @(Get-ChildItem -LiteralPath $PackageRoot -Recurse -File -Force | Where-Object { $_.Name -match $ForbiddenReleaseNamePattern })
    if ($forbidden.Count -gt 0) {
        throw "Forbidden credential-like filenames found in release: $($forbidden.FullName -join ', ')"
    }

    if ($PackageProfile -in @("demo", "final")) {
        $required = @(
            "requirements.txt",
            "start_dashboard.ps1",
            "DELIVERY_CHECKLIST.md",
            "scripts\verify_delivery.ps1",
            "dashboard\index.html",
            "dashboard\portfolio\index.html",
            "dashboard\raw-data\index.html",
            "ver3\dashboard\index.html",
            "ver4\dashboard\index.html",
            "outputs\ver3_0_dashboard_data\ver3_dashboard_data.js",
            "outputs\ver3_0_sleeve_diagnostics_report_pack\manifest.json",
            "outputs\ver3_0_stepC_robustness_stability_diagnostics\figures\ver3_0_stepC_candidate_nav_curves.png",
            "outputs\ver3_1_effective_zone_target_delta\analysis\target_delta_surface_contours\figures\159915_target_delta_coverage_sharpe_contours.png",
            "outputs\ver4_0_single_etf_cycle_cashflow\dashboard\ver4_dashboard_data.js",
            "outputs\ver4_1_delta_buyback\ver4_1_delta_buyback_cycle_daily_mtm.csv",
            "outputs\ver4_2_tp80_buyback\ver4_2_tp80_buyback_cycle_daily_mtm.csv"
        )
        foreach ($relativePath in $required) {
            if (-not (Test-Path -LiteralPath (Join-Path $PackageRoot $relativePath) -PathType Leaf)) {
                throw "Demo release is missing required dashboard file: $relativePath"
            }
        }
    }
    if ($PackageProfile -in @("inputs", "final")) {
        $required = @(
            "configs\ver2_downside_protection.yaml",
            "data\raw\etf_metadata.csv",
            "data\raw\etf_prices.csv",
            "data\raw\options_daily.csv",
            "data\source\delta_enriched_options.csv",
            "data\frozen_inputs\ver3_0_510050\ver2_1_daily_mtm.csv",
            "data\frozen_inputs\ver3_0_510050\ver2_1_periods_with_regime.csv",
            "outputs\ver3_0_stepA_moneyness_refined_daily_mtm_surface\summary\ver3_0_stepA_moneyness_refined_daily_mtm_surface_grid.csv",
            "outputs\ver3_0_stepA_moneyness_refined_daily_mtm_surface\daily\ver3_0_stepA_moneyness_refined_daily_mtm_daily_paths.csv"
        )
        foreach ($relativePath in $required) {
            if (-not (Test-Path -LiteralPath (Join-Path $PackageRoot $relativePath) -PathType Leaf)) {
                throw "Inputs release is missing required file: $relativePath"
            }
        }
    }
    if ($PackageProfile -eq "final") {
        foreach ($relativePath in $RawDataCatalogRelativeFiles) {
            if (-not (Test-Path -LiteralPath (Join-Path $PackageRoot $relativePath) -PathType Leaf)) {
                throw "Final release is missing raw-data catalog target: $relativePath"
            }
        }
        foreach ($relativePath in @(
            "data\sample_uploads\five_etf_daily\sample_manifest.json",
            "data\sample_uploads\five_etf_daily\510050\etf_daily.csv",
            "data\sample_uploads\five_etf_daily\510300\option_daily.csv",
            "data\sample_uploads\five_etf_daily\159919\option_contracts.csv",
            "data\sample_uploads\five_etf_daily\159915\option_daily.csv",
            "data\sample_uploads\five_etf_daily\159922\source_manifest.json",
            "outputs\final_acceptance\five_etf_acceptance.json"
        )) {
            if (-not (Test-Path -LiteralPath (Join-Path $PackageRoot $relativePath) -PathType Leaf)) {
                throw "Final release is missing five-ETF acceptance evidence: $relativePath"
            }
        }
    }
}

function New-ReleasePackage {
    param([ValidateSet("source", "demo", "inputs", "final")] [string] $PackageProfile)

    $releaseName = if ($PackageProfile -eq "final") {
        "covered_call_research_final_$ReleaseTag"
    }
    else {
        "covered_call_mini_${PackageProfile}_$ReleaseTag"
    }
    $stageName = "_stage_$($PackageProfile.Substring(0, 1))_$ReleaseTag"
    $packageRoot = Join-Path $OutputRoot $stageName
    $zipPath = Join-Path $OutputRoot "$releaseName.zip"
    if ((Test-Path -LiteralPath $packageRoot) -or (Test-Path -LiteralPath $zipPath)) {
        throw "Release target already exists: $packageRoot"
    }

    Write-Step "building $PackageProfile package"
    New-Item -ItemType Directory -Path $packageRoot -Force | Out-Null

    if ($PackageProfile -eq "inputs") {
        Copy-TreeRelative -RelativePath "configs" -PackageRoot $packageRoot
        Copy-InputFiles -PackageRoot $packageRoot
    }
    else {
        foreach ($file in @(
            "README.md",
            "PROJECT_GUIDE.md",
            "DATA_DICTIONARY.md",
            "DELIVERY_CHECKLIST.md",
            ".gitignore",
            "requirements.txt",
            "requirements-collectors.txt",
            "start_dashboard.ps1"
        )) {
            Copy-FileRelative -RelativePath $file -PackageRoot $packageRoot
        }
        foreach ($directory in @(
            "src",
            "tests",
            "scripts",
            "configs",
            "docs",
            "dashboard",
            "ver2_downside_protection",
            "ver3",
            "ver4"
        )) {
            Copy-TreeRelative -RelativePath $directory -PackageRoot $packageRoot
        }
    }

    if ($PackageProfile -in @("demo", "final")) {
        foreach ($directory in @(
            "outputs\final_report",
            "outputs\presentation",
            "outputs\project_overview",
            "outputs\ver3_0_dashboard_data",
            "outputs\ver3_0_sleeve_diagnostics_report_pack",
            "outputs\ver3_0_stepC_robustness_stability_diagnostics\figures",
            "outputs\ver3_1_effective_zone_target_delta\analysis\target_delta_surface_contours\figures",
            "outputs\ver3_1_effective_zone_target_delta\audit",
            "outputs\ver3_1_effective_zone_target_delta\dynamic",
            "outputs\ver3_1_effective_zone_target_delta\portfolio",
            "outputs\ver3_1_effective_zone_target_delta\reports",
            "outputs\ver3_1_effective_zone_target_delta\summary",
            "outputs\ver4_0_single_etf_cycle_cashflow",
            "outputs\ver4_1_delta_buyback",
            "outputs\ver4_1_ivrv_timing_diagnostics",
            "outputs\ver4_2_tp80_buyback",
            "outputs\ver4_chart_selections_510300_D40",
            "outputs\ver4_summary_report"
        )) {
            Copy-TreeRelative -RelativePath $directory -PackageRoot $packageRoot -Optional
        }
        foreach ($file in @(
            "outputs\ver3_1_effective_zone_target_delta\README.md",
            "outputs\ver3_1_effective_zone_target_delta\manifest.json"
        )) {
            Copy-FileRelative -RelativePath $file -PackageRoot $packageRoot -Optional
        }
    }

    if ($PackageProfile -eq "final") {
        Copy-InputFiles -PackageRoot $packageRoot
        Copy-TreeRelative -RelativePath "data\sample_uploads\five_etf_daily" -PackageRoot $packageRoot
        Copy-TreeRelative -RelativePath "outputs\final_acceptance" -PackageRoot $packageRoot
    }

    Assert-ReleaseSafety -PackageRoot $packageRoot -PackageProfile $PackageProfile
    Write-ReleaseMetadata -PackageRoot $packageRoot -PackageProfile $PackageProfile
    Compress-Archive -Path (Join-Path $packageRoot "*") -DestinationPath $zipPath -CompressionLevel Optimal
    $zipHash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
    Set-Content -LiteralPath "$zipPath.sha256" -Value "$zipHash  $([System.IO.Path]::GetFileName($zipPath))" -Encoding ASCII

    $packageFiles = @(Get-ChildItem -LiteralPath $packageRoot -Recurse -File -Force)
    $packageBytes = ($packageFiles | Measure-Object -Property Length -Sum).Sum
    Remove-Item -LiteralPath $packageRoot -Recurse -Force
    Write-Step "$PackageProfile package ready: $zipPath"
    [pscustomobject]@{
        profile = $PackageProfile
        directory = "archive only"
        archive = $zipPath
        files = $packageFiles.Count
        uncompressed_mib = [Math]::Round($packageBytes / 1MB, 2)
        archive_mib = [Math]::Round((Get-Item -LiteralPath $zipPath).Length / 1MB, 2)
        sha256 = $zipHash
    }
}

New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
$profiles = switch ($Profile) {
    "Source" { @("source") }
    "Demo" { @("demo") }
    "Inputs" { @("inputs") }
    "Final" { @("final") }
    default { @("source", "demo", "inputs", "final") }
}

$results = foreach ($packageProfile in $profiles) {
    New-ReleasePackage -PackageProfile $packageProfile
}
$results | Format-Table -AutoSize
