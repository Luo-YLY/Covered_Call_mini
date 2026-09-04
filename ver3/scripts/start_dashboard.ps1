param(
    [int] $Port = 8765,
    [switch] $SkipDataRefresh,
    [switch] $NoOpen,
    [switch] $StrictPort,
    [switch] $ForceNew,
    [switch] $DryRun
)

$ErrorActionPreference = "Stop"

function Test-LocalPortAvailable {
    param([int] $CandidatePort)

    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $CandidatePort)
    try {
        $listener.Start()
        return $true
    }
    catch {
        return $false
    }
    finally {
        try {
            $listener.Stop()
        }
        catch {
        }
    }
}

function Resolve-DashboardPort {
    param(
        [int] $RequestedPort,
        [bool] $RequireExactPort
    )

    if (Test-LocalPortAvailable -CandidatePort $RequestedPort) {
        return $RequestedPort
    }

    if ($RequireExactPort) {
        throw "Port $RequestedPort is already in use. Re-run with another -Port or omit -StrictPort."
    }

    for ($candidate = $RequestedPort + 1; $candidate -le $RequestedPort + 50; $candidate++) {
        if (Test-LocalPortAvailable -CandidatePort $candidate) {
            return $candidate
        }
    }

    throw "No available local port found from $RequestedPort to $($RequestedPort + 50)."
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..\..")
$DashboardIndex = Join-Path $RepoRoot "ver3\dashboard\index.html"
$DashboardDataBuilder = Join-Path $RepoRoot "ver3\scripts\python\build_ver3_dashboard_data.py"
$DashboardData = Join-Path $RepoRoot "outputs\ver3_0_dashboard_data\ver3_dashboard_data.js"
$RuntimeDir = Join-Path $RepoRoot "ver3\.runtime"
$ManifestPath = Join-Path $RuntimeDir "dashboard_server.json"

if (-not (Test-Path $DashboardIndex)) {
    throw "Dashboard index not found: $DashboardIndex"
}
if (-not (Test-Path $DashboardDataBuilder)) {
    throw "Dashboard data builder not found: $DashboardDataBuilder"
}

Push-Location $RepoRoot
try {
    if ((-not $ForceNew) -and (Test-Path $ManifestPath)) {
        $ExistingServer = $null
        try {
            $ExistingServer = Get-Content -Path $ManifestPath -Raw | ConvertFrom-Json
        }
        catch {
            $ExistingServer = $null
        }

        if ($ExistingServer -and $ExistingServer.pid) {
            $ExistingProcess = Get-Process -Id ([int] $ExistingServer.pid) -ErrorAction SilentlyContinue
            if ($ExistingProcess) {
                $ExistingUrl = [string] $ExistingServer.url
                if (-not $ExistingUrl) {
                    $ExistingUrl = "http://127.0.0.1:$($ExistingServer.port)/ver3/dashboard/"
                }

                if ($DryRun) {
                    Write-Host "Existing dashboard server detected."
                    Write-Host "URL: $ExistingUrl"
                    Write-Host "PID: $($ExistingProcess.Id)"
                    Write-Host "Manifest: $ManifestPath"
                    return
                }

                if (-not $NoOpen) {
                    Start-Process $ExistingUrl
                }

                Write-Host "ver3 dashboard server already running."
                Write-Host "URL: $ExistingUrl"
                Write-Host "PID: $($ExistingProcess.Id)"
                Write-Host "Manifest: $ManifestPath"
                return
            }
        }
    }

    $SelectedPort = Resolve-DashboardPort -RequestedPort $Port -RequireExactPort ([bool] $StrictPort)
    $Url = "http://127.0.0.1:$SelectedPort/ver3/dashboard/"

    if ($DryRun) {
        Write-Host "Dry run only."
        Write-Host "Data refresh: $(-not [bool] $SkipDataRefresh)"
        Write-Host "Server root: $RepoRoot"
        Write-Host "URL: $Url"
        return
    }

    if (-not $SkipDataRefresh) {
        Write-Host "Refreshing dashboard data..."
        python $DashboardDataBuilder
        if ($LASTEXITCODE -ne 0) {
            throw "Dashboard data refresh failed with exit code $LASTEXITCODE."
        }
    }
    elseif (-not (Test-Path $DashboardData)) {
        throw "Dashboard data file is missing. Run without -SkipDataRefresh first: $DashboardData"
    }

    $ServerArgs = @(
        "-m",
        "http.server",
        "$SelectedPort",
        "--bind",
        "127.0.0.1"
    )

    $Process = Start-Process `
        -FilePath "python" `
        -ArgumentList $ServerArgs `
        -WorkingDirectory $RepoRoot `
        -WindowStyle Hidden `
        -PassThru

    New-Item -ItemType Directory -Path $RuntimeDir -Force | Out-Null
    $Manifest = [ordered]@{
        url = $Url
        pid = $Process.Id
        port = $SelectedPort
        repo_root = "$RepoRoot"
        dashboard_index = "ver3\dashboard\index.html"
        dashboard_data = "outputs\ver3_0_dashboard_data\ver3_dashboard_data.js"
        data_refreshed = (-not [bool] $SkipDataRefresh)
        started_at = (Get-Date).ToString("s")
    }
    $Manifest | ConvertTo-Json -Depth 4 | Set-Content -Path $ManifestPath -Encoding UTF8

    if (-not $NoOpen) {
        Start-Process $Url
    }

    Write-Host "ver3 dashboard server started."
    Write-Host "URL: $Url"
    Write-Host "PID: $($Process.Id)"
    Write-Host "Manifest: $ManifestPath"
}
finally {
    Pop-Location
}
