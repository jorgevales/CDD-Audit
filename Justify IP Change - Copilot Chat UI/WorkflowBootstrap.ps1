param(
    [ValidateSet("Setup", "Start", "Test")]
    [string]$Action = "Setup"
)

# Compatibility entrypoint retained for existing shortcuts. New launchers call Launcher.ps1 directly.
& (Join-Path $PSScriptRoot 'Launcher.ps1') -Action $Action
exit $LASTEXITCODE

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSCommandPath
$ProjectName = "Justify IP Change - Copilot Chat UI"
$MinimumPython = [version]"3.10"

function Get-SafePathPart([string]$Value) {
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($Value.ToLowerInvariant())
        (($sha.ComputeHash($bytes) | ForEach-Object { $_.ToString("x2") }) -join "").Substring(0, 16)
    } finally { $sha.Dispose() }
}

function Get-UserBase {
    if (-not $env:LOCALAPPDATA) { throw "Windows LocalAppData is unavailable for this user." }
    $path = Join-Path $env:LOCALAPPDATA "CDD Audit\JustifyIPChangeCopilotChatUI"
    New-Item -ItemType Directory -Path $path -Force | Out-Null
    return $path
}

function Find-Python {
    $configured = Join-Path $ProjectRoot "python_path.txt"
    $candidates = New-Object System.Collections.Generic.List[string]
    if (Test-Path -LiteralPath $configured -PathType Leaf) {
        $line = Get-Content -LiteralPath $configured | Where-Object { $_.Trim() -and -not $_.Trim().StartsWith("#") } | Select-Object -First 1
        if ($line) { $candidates.Add($line.Trim().Trim('"')) }
    }
    try {
        $py = Get-Command py.exe -ErrorAction Stop
        foreach ($line in @(& $py.Source -0p 2>$null)) {
            if ($line -match "([A-Za-z]:\\.*python(?:3)?\.exe)\s*$") { $candidates.Add($Matches[1]) }
        }
    } catch { }
    foreach ($name in @("python.exe", "python3.exe")) {
        try { (Get-Command $name -ErrorAction Stop).Source | ForEach-Object { $candidates.Add($_) } } catch { }
    }
    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
        $versionText = & $candidate -E -s -c "import sys; print('.'.join(map(str, sys.version_info[:3])))" 2>$null
        if ($LASTEXITCODE -eq 0 -and [version]$versionText -ge $MinimumPython) { return (Resolve-Path -LiteralPath $candidate).Path }
    }
    throw "Python 3.10 or newer was not found. Install an approved Python or place its full path in python_path.txt beside Setup.cmd."
}

function Invoke-Checked([string]$FilePath, [string[]]$Arguments, [string]$Description) {
    Write-Host ""
    Write-Host $Description
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Description failed with exit code $LASTEXITCODE." }
}

$UserBase = Get-UserBase
$ProjectId = Get-SafePathPart $ProjectRoot
$EnvRoot = Join-Path $UserBase ("envs\" + $ProjectId)
$VenvPath = Join-Path $EnvRoot ".venv"
$VenvPython = Join-Path $VenvPath "Scripts\python.exe"
$LogRoot = Join-Path $UserBase "logs"
New-Item -ItemType Directory -Path $EnvRoot -Force | Out-Null
New-Item -ItemType Directory -Path $LogRoot -Force | Out-Null
$LogPath = Join-Path $LogRoot ((Get-Date -Format "yyyyMMdd-HHmmss") + "-$PID.log")
$TranscriptStarted = $false
try { Start-Transcript -LiteralPath $LogPath -Force | Out-Null; $TranscriptStarted = $true } catch { }

try {
    Write-Host $ProjectName
    Write-Host "Project folder: $ProjectRoot"
    Write-Host "Diagnostic log: $LogPath"
    $lockPath = Join-Path $EnvRoot "environment.lock"
    $lock = [System.IO.File]::Open($lockPath, [System.IO.FileMode]::OpenOrCreate, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
    try {
        if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf) -and $Action -ne "Setup") {
            throw "This user's environment is not installed. Run Setup.cmd once, then retry."
        }
        if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
            $basePython = Find-Python
            Invoke-Checked $basePython @("-E", "-s", "-m", "venv", $VenvPath) "Creating this user's private environment"
        }
        if ($Action -eq "Setup") {
            Invoke-Checked $VenvPython @("-E", "-s", "-m", "pip", "install", "--requirement", (Join-Path $ProjectRoot "requirements.txt")) "Checking required packages"
            Invoke-Checked $VenvPython @("-E", "-s", "-m", "pip", "check") "Checking package compatibility"
        } else {
            Invoke-Checked $VenvPython @("-E", "-s", "-m", "pip", "check") "Checking installed package compatibility"
            Invoke-Checked $VenvPython @("-E", "-s", "-c", "import openpyxl, playwright; print('Required packages are available.')") "Checking required imports"
        }
    } finally { $lock.Dispose() }

    $env:PYTHONDONTWRITEBYTECODE = "1"
    Set-Location -LiteralPath $ProjectRoot
    if ($Action -eq "Start") {
        & $VenvPython -E -s (Join-Path $ProjectRoot "app.py")
        if ($LASTEXITCODE -ne 0) { throw "The application stopped with exit code $LASTEXITCODE." }
    } elseif ($Action -eq "Test") {
        Invoke-Checked $VenvPython @("-E", "-s", "-m", "unittest", "discover", "-s", "tests", "-v") "Running offline tests"
    } else {
        Write-Host ""
        Write-Host "Setup is complete for this Windows user."
        Write-Host "Environment: $VenvPath"
    }
    if ($TranscriptStarted) { Stop-Transcript | Out-Null; $TranscriptStarted = $false }
    exit 0
} catch {
    Write-Host ""
    Write-Host "The requested action did not finish."
    Write-Host $_.Exception.Message
    Write-Host "Diagnostic log: $LogPath"
    if ($TranscriptStarted) { try { Stop-Transcript | Out-Null } catch { }; $TranscriptStarted = $false }
    exit 1
}
