param(
    [int]$BackendPort = 8100,
    [int]$FrontendPort = 8080,
    [string]$ApiHost = $env:API_HOST,
    [string]$UvBin = $env:UV_BIN
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$FrontendDir = Join-Path $ProjectRoot "ocr_frontend"
$FrontendConfigFile = Join-Path $FrontendDir "config.js"
$FrontendServer = Join-Path $FrontendDir "server.py"
$RootEnvFile = Join-Path (Split-Path -Parent $ProjectRoot) "..\.env"
$UvCacheDir = if ($env:UV_CACHE_DIR) { $env:UV_CACHE_DIR } else { "C:\Temp\uv-cache" }

function Load-DotEnv {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        return
    }

    Get-Content $Path | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) {
            return
        }
        $parts = $line -split "=", 2
        if ($parts.Count -ne 2) {
            return
        }
        [System.Environment]::SetEnvironmentVariable($parts[0], $parts[1])
    }
}

function Get-PreferredIPv4 {
    $candidates = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object {
            $_.IPAddress -ne "127.0.0.1" -and
            $_.PrefixOrigin -ne "WellKnown"
        } |
        Sort-Object InterfaceMetric

    if ($candidates) {
        return $candidates[0].IPAddress
    }

    return "127.0.0.1"
}

function Find-PortPids {
    param([int]$Port)

    $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $connections) {
        return @()
    }

    return $connections | Select-Object -ExpandProperty OwningProcess -Unique
}

function Ensure-PortAvailable {
    param(
        [int]$Port,
        [string]$Label
    )

    $pids = Find-PortPids -Port $Port
    if (-not $pids -or $pids.Count -eq 0) {
        return
    }

    Write-Host "$Label port $Port is already in use. Checking existing process..."
    foreach ($pid in $pids) {
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $pid" -ErrorAction SilentlyContinue
        if ($proc -and $proc.CommandLine -like "*$ProjectRoot*") {
            Write-Host "Stopping existing OCR process on port $Port (PID: $pid)"
            Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
        } else {
            throw "Port $Port is occupied by a non-OCR process (PID: $pid)."
        }
    }

    Start-Sleep -Seconds 1

    $remaining = Find-PortPids -Port $Port
    if ($remaining -and $remaining.Count -gt 0) {
        throw "Port $Port is still in use: $($remaining -join ', ')"
    }
}

Load-DotEnv -Path $RootEnvFile

if (-not $ApiHost) {
    $ApiHost = Get-PreferredIPv4
}

if (-not $UvBin) {
    $uvCommand = Get-Command uv -ErrorAction SilentlyContinue
    if (-not $uvCommand) {
        throw "uv not found. Please install uv or set UV_BIN."
    }
    $UvBin = $uvCommand.Source
}

if ($BackendPort -lt 1 -or $BackendPort -gt 65535) {
    throw "Invalid backend port: $BackendPort"
}

if ($FrontendPort -lt 1 -or $FrontendPort -gt 65535) {
    throw "Invalid frontend port: $FrontendPort"
}

New-Item -ItemType Directory -Force -Path $UvCacheDir | Out-Null

Ensure-PortAvailable -Port $BackendPort -Label "Backend"
Ensure-PortAvailable -Port $FrontendPort -Label "Frontend"

@"
window.OCR_APP_CONFIG = {
  apiBaseUrl: "http://$ApiHost`:$BackendPort"
};
"@ | Set-Content -Path $FrontendConfigFile -Encoding UTF8

Write-Host "Backend URL: http://$ApiHost`:$BackendPort"
Write-Host "Frontend URL: http://$ApiHost`:$FrontendPort"
Write-Host "Web page: http://$ApiHost`:$FrontendPort/index.html"

$backendArgs = @(
    "run", "python", "-m", "flask",
    "--app", "ocr_backend.app",
    "run",
    "--host", "0.0.0.0",
    "--port", "$BackendPort"
)

$frontendArgs = @(
    $FrontendServer,
    "--host", "0.0.0.0",
    "--port", "$FrontendPort"
)

$env:UV_CACHE_DIR = $UvCacheDir
$env:PYTHONPATH = $ProjectRoot

$backend = Start-Process -FilePath $UvBin -ArgumentList $backendArgs -WorkingDirectory $ProjectRoot -PassThru
$frontend = Start-Process -FilePath "python" -ArgumentList $frontendArgs -WorkingDirectory $FrontendDir -PassThru

try {
    Wait-Process -Id $backend.Id, $frontend.Id
}
finally {
    foreach ($proc in @($backend, $frontend)) {
        if ($proc -and -not $proc.HasExited) {
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        }
    }
}
