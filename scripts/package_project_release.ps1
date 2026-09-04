[CmdletBinding()]
param(
    [ValidateSet("All", "Source", "Demo", "Inputs")]
    [string] $Profile = "All",
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

function Write-Step {
    param([string] $Message)
    Write-Host "[project-release] $Message"
}

function Test-SkippedFile {
    param([System.IO.FileInfo] $File, [string] $SourceBase)

    $relative = [System.IO.Path]::GetRelativePath($SourceBase, $File.FullName)
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
        $withinTree = [System.IO.Path]::GetRelativePath($source, $file.FullName)
        $destination = Join-Path (Join-Path $PackageRoot $RelativePath) $withinTree
        New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
        Copy-Item -LiteralPath $file.FullName -Destination $destination -Force
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
        "source" { "源码、测试、非秘密配置和文档；不含原始行情、派生大表或生成结果。" }
        "demo" { "源码包内容，加上 ver3/ver4 看板数据、ver3.1 摘要、ver4 汇总报告、汇报材料和精选展示图表。" }
        "inputs" { "ver3/ver4 主线运行所需的冻结 ETF 与期权输入数据；不含访问凭据和本机接口配置。" }
    }

    $readme = @"
# covered_call_mini $PackageProfile release

生成时间：$(Get-Date -Format "yyyy-MM-dd HH:mm:ss zzz")

## 范围

$scopeText

## 研究边界

- 本包由当前工作区快照生成；是否对应干净 Git 提交请查看 `GIT_SNAPSHOT.txt`。
- 本包不包含 `config/*.txt`、`.env`、访问令牌、密码或本机接口配置。
- `source`、`demo`、`inputs` 三个包合并构成交接发布组；正式复现仍需在目标机器复核 Python 环境并重跑验收。
- 所有研究输出仅用于研究与展示，不构成交易指令。

## 演示看板

`demo` 包可在解压目录运行：

    python -m http.server 8765 --bind 127.0.0.1

然后访问：

- `http://127.0.0.1:8765/ver3/dashboard/`
- `http://127.0.0.1:8765/ver4/dashboard/`

## 完整性

`FILE_INDEX.csv` 记录包内文件的相对路径、字节数和 SHA-256。ZIP 自身哈希位于相邻的 `.sha256` 文件。
"@
    Set-Content -LiteralPath (Join-Path $PackageRoot "RELEASE_README.md") -Value $readme -Encoding UTF8
    Set-Content -LiteralPath (Join-Path $PackageRoot "GIT_SNAPSHOT.txt") -Value (Get-GitSnapshot) -Encoding UTF8

    $files = Get-ChildItem -LiteralPath $PackageRoot -Recurse -File -Force | Sort-Object FullName
    $indexRows = foreach ($file in $files) {
        [pscustomobject]@{
            path = [System.IO.Path]::GetRelativePath($PackageRoot, $file.FullName).Replace('\', '/')
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

    if ($PackageProfile -eq "demo") {
        $required = @(
            "ver3\dashboard\index.html",
            "ver4\dashboard\index.html",
            "outputs\ver3_0_dashboard_data\ver3_dashboard_data.js",
            "outputs\ver3_0_sleeve_diagnostics_report_pack\manifest.json",
            "outputs\ver3_0_stepC_robustness_stability_diagnostics\figures\ver3_0_stepC_candidate_nav_curves.png",
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
    elseif ($PackageProfile -eq "inputs") {
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
}

function New-ReleasePackage {
    param([ValidateSet("source", "demo", "inputs")] [string] $PackageProfile)

    $releaseName = "covered_call_mini_${PackageProfile}_$ReleaseTag"
    $packageRoot = Join-Path $OutputRoot $releaseName
    $zipPath = "$packageRoot.zip"
    if ((Test-Path -LiteralPath $packageRoot) -or (Test-Path -LiteralPath $zipPath)) {
        throw "Release target already exists: $packageRoot"
    }

    Write-Step "building $PackageProfile package"
    New-Item -ItemType Directory -Path $packageRoot -Force | Out-Null

    if ($PackageProfile -eq "inputs") {
        Copy-TreeRelative -RelativePath "configs" -PackageRoot $packageRoot
        foreach ($file in @(
            "data\raw\etf_metadata.csv",
            "data\raw\etf_prices.csv",
            "data\raw\options.csv",
            "data\raw\options_daily.csv",
            "data\source\delta_enriched_options.csv",
            "data\frozen_inputs\ver3_0_510050\ver2_1_daily_mtm.csv",
            "data\frozen_inputs\ver3_0_510050\ver2_1_periods_with_regime.csv",
            "outputs\ver3_0_stepA_moneyness_refined_daily_mtm_surface\summary\ver3_0_stepA_moneyness_refined_daily_mtm_surface_grid.csv",
            "outputs\ver3_0_stepA_moneyness_refined_daily_mtm_surface\daily\ver3_0_stepA_moneyness_refined_daily_mtm_daily_paths.csv"
        )) {
            Copy-FileRelative -RelativePath $file -PackageRoot $packageRoot
        }
    }
    else {
        foreach ($file in @("README.md", "DATA_DICTIONARY.md", ".gitignore")) {
            Copy-FileRelative -RelativePath $file -PackageRoot $packageRoot
        }
        foreach ($directory in @(
            "src",
            "tests",
            "scripts",
            "configs",
            "docs",
            "ver2_downside_protection",
            "ver3",
            "ver4"
        )) {
            Copy-TreeRelative -RelativePath $directory -PackageRoot $packageRoot
        }
    }

    if ($PackageProfile -eq "demo") {
        foreach ($directory in @(
            "outputs\final_report",
            "outputs\presentation",
            "outputs\project_overview",
            "outputs\ver3_0_dashboard_data",
            "outputs\ver3_0_sleeve_diagnostics_report_pack",
            "outputs\ver3_0_stepC_robustness_stability_diagnostics\figures",
            "outputs\ver3_1_effective_zone_target_delta\audit",
            "outputs\ver3_1_effective_zone_target_delta\dynamic",
            "outputs\ver3_1_effective_zone_target_delta\portfolio",
            "outputs\ver3_1_effective_zone_target_delta\reports",
            "outputs\ver3_1_effective_zone_target_delta\summary",
            "outputs\ver4_0_single_etf_cycle_cashflow\dashboard",
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

    Assert-ReleaseSafety -PackageRoot $packageRoot -PackageProfile $PackageProfile
    Write-ReleaseMetadata -PackageRoot $packageRoot -PackageProfile $PackageProfile
    Compress-Archive -LiteralPath $packageRoot -DestinationPath $zipPath -CompressionLevel Optimal
    $zipHash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
    Set-Content -LiteralPath "$zipPath.sha256" -Value "$zipHash  $([System.IO.Path]::GetFileName($zipPath))" -Encoding ASCII

    $packageFiles = @(Get-ChildItem -LiteralPath $packageRoot -Recurse -File -Force)
    $packageBytes = ($packageFiles | Measure-Object -Property Length -Sum).Sum
    Write-Step "$PackageProfile package ready: $zipPath"
    [pscustomobject]@{
        profile = $PackageProfile
        directory = $packageRoot
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
    default { @("source", "demo", "inputs") }
}

$results = foreach ($packageProfile in $profiles) {
    New-ReleasePackage -PackageProfile $packageProfile
}
$results | Format-Table -AutoSize
