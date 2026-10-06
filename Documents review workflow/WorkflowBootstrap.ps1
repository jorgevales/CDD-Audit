param(
    [ValidateSet("Setup", "Start", "StartDemo", "Test")]
    [string]$Action = "Setup"
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

$BootstrapPath = $env:CDD_BOOTSTRAP
if (-not $BootstrapPath) {
    $psCommandPathVariable = Get-Variable -Name PSCommandPath -ErrorAction SilentlyContinue
    if ($psCommandPathVariable -and $psCommandPathVariable.Value) {
        $BootstrapPath = $psCommandPathVariable.Value
    }
}
if (-not $BootstrapPath -and $MyInvocation.MyCommand -and ($MyInvocation.MyCommand | Get-Member -Name Path -MemberType Properties)) {
    $BootstrapPath = $MyInvocation.MyCommand.Path
}
$ProjectName = "CDD Audit Documents Review Workflow"
$MinimumPython = [version]"3.10"

function Get-SafePathPart {
    param([string]$Value)
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($Value.ToLowerInvariant())
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        (($sha.ComputeHash($bytes) | ForEach-Object { $_.ToString("x2") }) -join "").Substring(0, 16)
    } finally {
        $sha.Dispose()
    }
}

function Get-FileHashText {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Required file is missing: $Path"
    }
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Get-WritableBase {
    $candidates = New-Object System.Collections.Generic.List[string]
    if ($env:LOCALAPPDATA) { $candidates.Add($env:LOCALAPPDATA) }
    if ($env:USERPROFILE) { $candidates.Add((Join-Path $env:USERPROFILE "AppData\Local")) }
    foreach ($candidate in $candidates) {
        try {
            $root = Join-Path $candidate "CDD Audit\DocumentsReviewWorkflow"
            New-Item -ItemType Directory -Path $root -Force | Out-Null
            $testFile = Join-Path $root ("write-test-{0}.tmp" -f ([guid]::NewGuid().ToString("N")))
            Set-Content -LiteralPath $testFile -Value "ok" -Encoding ASCII
            Remove-Item -LiteralPath $testFile -Force
            return $root
        } catch {
            continue
        }
    }
    throw "No writable per-user application-data location was available. Ask support to check your Windows profile LocalAppData folder."
}

$script:TranscriptStarted = $false
try {
    if (-not $BootstrapPath) {
        throw "The bootstrap script path could not be determined."
    }
    $ProjectRoot = Split-Path -Parent (Resolve-Path -LiteralPath $BootstrapPath).Path
    Set-Location -LiteralPath $ProjectRoot
    $RequirementsPath = Join-Path $ProjectRoot "requirements.txt"
    $EntryPointPath = Join-Path $ProjectRoot "app.py"
    $ProjectId = Get-SafePathPart $ProjectRoot
    $UserBase = Get-WritableBase
    $EnvRoot = Join-Path $UserBase ("envs\{0}" -f $ProjectId)
    $VenvPath = Join-Path $EnvRoot ".venv"
    $StatePath = Join-Path $EnvRoot "environment.json"
    $LogDir = Join-Path $UserBase "logs"
    New-Item -ItemType Directory -Path $EnvRoot -Force | Out-Null
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
    $LogPath = Join-Path $LogDir ("{0}-{1}-{2}.log" -f $ProjectId, (Get-Date -Format "yyyyMMdd-HHmmss"), $PID)
    try {
        Start-Transcript -LiteralPath $LogPath -Force | Out-Null
        $script:TranscriptStarted = $true
    } catch {
        Write-Host "Diagnostic logging could not start: $($_.Exception.Message)"
    }
} catch {
    Write-Host $ProjectName
    Write-Host ""
    Write-Host "The requested action did not finish."
    Write-Host $_.Exception.Message
    exit 1
}

function Write-Info {
    param([string]$Message)
    Write-Host $Message
}

function Stop-Logging {
    if ($script:TranscriptStarted) {
        try { Stop-Transcript | Out-Null } catch { }
        $script:TranscriptStarted = $false
    }
}

function Invoke-External {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$Description,
        [switch]$AllowFailure
    )
    Write-Info ""
    Write-Info $Description
    Write-Info ("> {0} {1}" -f $FilePath, ($Arguments -join " "))
    $previousPreference = $ErrorActionPreference
    try {
        # Windows PowerShell can treat native stderr as an error before we check its exit code.
        $ErrorActionPreference = "Continue"
        $output = & $FilePath @Arguments 2>&1
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    foreach ($line in $output) { Write-Host $line }
    if ($exitCode -ne 0 -and -not $AllowFailure) {
        throw "$Description failed with exit code $exitCode."
    }
    [pscustomobject]@{
        ExitCode = $exitCode
        Output = (($output | ForEach-Object { $_.ToString() }) -join [Environment]::NewLine)
    }
}

function Add-Candidate {
    param(
        [System.Collections.ArrayList]$Candidates,
        [string]$Path,
        [string]$Source,
        [int]$Rank
    )
    if (-not $Path) { return }
    $clean = $Path.Trim().Trim('"')
    if (-not $clean) { return }
    try {
        $resolved = (Resolve-Path -LiteralPath $clean -ErrorAction Stop).Path
    } catch {
        Write-Info "Python candidate from $Source was not found: $clean"
        return
    }
    if ([System.IO.Path]::GetFileName($resolved).ToLowerInvariant() -notin @("python.exe", "python3.exe")) { return }
    if ($resolved.ToLowerInvariant().Contains("\windowsapps\")) {
        Write-Info "Skipping Windows app installer alias: $resolved"
        return
    }
    if ($resolved.ToLowerInvariant().Contains("\.venv\") -or $resolved.ToLowerInvariant().EndsWith("\scripts\python.exe")) { return }
    if (-not ($Candidates | Where-Object { $_.Path -ieq $resolved })) {
        [void]$Candidates.Add([pscustomobject]@{ Path = $resolved; Source = $Source; Rank = $Rank })
    }
}

function Get-PyLauncherCandidates {
    $paths = New-Object System.Collections.Generic.List[string]
    try {
        $py = Get-Command py.exe -ErrorAction Stop
        $output = & $py.Source -0p 2>$null
        foreach ($line in $output) {
            if ($line -match "([A-Za-z]:\\.*python(?:3)?\.exe)\s*$") {
                $paths.Add($Matches[1])
            }
        }
    } catch {
        return @()
    }
    $paths
}

function Search-PythonBelow {
    param(
        [string]$BasePath,
        [int]$MaxDepth,
        [System.Diagnostics.Stopwatch]$Stopwatch,
        [int]$MaxSeconds
    )
    $found = New-Object System.Collections.Generic.List[string]
    if (-not (Test-Path -LiteralPath $BasePath -PathType Container)) { return $found }
    $queue = New-Object System.Collections.Queue
    $queue.Enqueue([pscustomobject]@{ Path = $BasePath; Depth = 0 })
    while ($queue.Count -gt 0 -and $Stopwatch.Elapsed.TotalSeconds -lt $MaxSeconds -and $found.Count -lt 50) {
        $item = $queue.Dequeue()
        try {
            Get-ChildItem -LiteralPath $item.Path -Filter python.exe -File -ErrorAction SilentlyContinue |
                ForEach-Object { $found.Add($_.FullName) }
            if ($item.Depth -lt $MaxDepth) {
                Get-ChildItem -LiteralPath $item.Path -Directory -ErrorAction SilentlyContinue |
                    Where-Object {
                        $_.Name -notin @(".git", ".venv", "__pycache__", "node_modules", "dist", "build", "logs", "diagnostics")
                    } |
                    ForEach-Object {
                        $queue.Enqueue([pscustomobject]@{ Path = $_.FullName; Depth = ($item.Depth + 1) })
                    }
            }
        } catch {
            continue
        }
    }
    $found
}

function Add-SharedDriveCandidates {
    param([System.Collections.ArrayList]$Candidates)
    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    $root = [System.IO.Path]::GetPathRoot($ProjectRoot)
    $bases = New-Object System.Collections.Generic.List[string]
    $current = $ProjectRoot
    while ($current -and $current.StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase)) {
        $bases.Add($current)
        $parent = Split-Path -Parent $current
        if ($parent -eq $current) { break }
        $current = $parent
    }
    try {
        Get-ChildItem -LiteralPath $root -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match "python|tools|apps|software|portable" } |
            ForEach-Object { $bases.Add($_.FullName) }
    } catch { }

    foreach ($base in ($bases | Select-Object -Unique)) {
        if ($stopwatch.Elapsed.TotalSeconds -ge 30) { break }
        foreach ($path in (Search-PythonBelow -BasePath $base -MaxDepth 4 -Stopwatch $stopwatch -MaxSeconds 30)) {
            Add-Candidate -Candidates $Candidates -Path $path -Source "same shared drive search" -Rank 40
        }
    }
}

function Test-PythonCandidate {
    param($Candidate)
    $code = "import importlib.util, sys; print(sys.executable); print('%d.%d.%d' % sys.version_info[:3]); print('1' if importlib.util.find_spec('venv') else '0'); print('1' if importlib.util.find_spec('ensurepip') else '0')"
    try {
        $output = & $Candidate.Path -c $code 2>&1
        if ($LASTEXITCODE -ne 0 -or -not $output) {
            $reason = (($output | ForEach-Object { $_.ToString() }) -join " ").Trim()
            if (-not $reason) { $reason = "it could not run a validation command" }
            return [pscustomobject]@{ Candidate = $Candidate; Ok = $false; Reason = $reason }
        }
        $lines = @($output | ForEach-Object { $_.ToString().Trim() } | Where-Object { $_ })
        if ($lines.Count -lt 4) {
            return [pscustomobject]@{ Candidate = $Candidate; Ok = $false; Reason = "the validation command returned incomplete output" }
        }
        $version = [version]$lines[1]
        if ($version -lt $MinimumPython) {
            return [pscustomobject]@{ Candidate = $Candidate; Ok = $false; Reason = "Python $version is below the supported minimum $MinimumPython" }
        }
        if ($lines[2] -ne "1") {
            return [pscustomobject]@{ Candidate = $Candidate; Ok = $false; Reason = "the Python venv module is unavailable" }
        }
        [pscustomobject]@{
            Candidate = $Candidate
            Ok = $true
            Reason = "ok"
            Version = $version
            Executable = $lines[0]
            HasEnsurePip = ($lines[3] -eq "1")
        }
    } catch {
        [pscustomobject]@{ Candidate = $Candidate; Ok = $false; Reason = $_.Exception.Message }
    }
}

function Find-Python {
    $candidates = New-Object System.Collections.ArrayList
    $configuredPath = Join-Path $ProjectRoot "python_path.txt"
    if (Test-Path -LiteralPath $configuredPath -PathType Leaf) {
        $configured = (Get-Content -LiteralPath $configuredPath -ErrorAction Stop | Where-Object { $_.Trim() -and -not $_.Trim().StartsWith("#") } | Select-Object -First 1)
        Add-Candidate -Candidates $candidates -Path $configured -Source "python_path.txt" -Rank 1
        if ($candidates.Count -eq 0) { throw "python_path.txt does not point to an available Python. Ask support to correct it." }
    } elseif ($env:CDD_AUDIT_PYTHON) {
        Add-Candidate -Candidates $candidates -Path $env:CDD_AUDIT_PYTHON -Source "CDD_AUDIT_PYTHON" -Rank 2
        if ($candidates.Count -eq 0) { throw "CDD_AUDIT_PYTHON does not point to an available Python. Ask support to correct it." }
    }
    if ($candidates.Count -gt 0) {
        $configuredResult = Test-PythonCandidate -Candidate $candidates[0]
        if (-not $configuredResult.Ok) { throw "The configured Python is incompatible: $($configuredResult.Reason)" }
        return $configuredResult
    }
    foreach ($path in (Get-PyLauncherCandidates)) {
        Add-Candidate -Candidates $candidates -Path $path -Source "Windows Python launcher" -Rank 10
    }
    foreach ($commandName in @("python.exe", "python3.exe")) {
        try {
            Get-Command $commandName -All -ErrorAction Stop |
                ForEach-Object { Add-Candidate -Candidates $candidates -Path $_.Source -Source "PATH" -Rank 20 }
        } catch { }
    }
    $localResults = @($candidates | ForEach-Object { Test-PythonCandidate -Candidate $_ })
    $localPython = $localResults | Where-Object { $_.Ok } |
        Sort-Object @{ Expression = { $_.Candidate.Rank }; Ascending = $true }, @{ Expression = { $_.Version }; Ascending = $false } |
        Select-Object -First 1
    if ($localPython) { return $localPython }
    Add-SharedDriveCandidates -Candidates $candidates

    if ($candidates.Count -eq 0) {
        throw "No Python interpreter was found. Install an approved Python, or create python_path.txt next to Setup.cmd containing the full path to python.exe."
    }

    $validated = @()
    foreach ($candidate in $candidates) {
        $result = Test-PythonCandidate -Candidate $candidate
        $validated += $result
        if ($result.Ok) {
            Write-Info ("Validated Python {0} from {1}: {2}" -f $result.Version, $candidate.Source, $candidate.Path)
        } else {
            Write-Info ("Rejected Python from {0}: {1} ({2})" -f $candidate.Source, $candidate.Path, $result.Reason)
        }
    }

    $configuredOk = $validated | Where-Object { $_.Ok -and $_.Candidate.Rank -le 2 } | Sort-Object { $_.Candidate.Rank } | Select-Object -First 1
    if ($configuredOk) { return $configuredOk }

    $normalOk = $validated | Where-Object { $_.Ok -and $_.Candidate.Rank -lt 40 } |
        Sort-Object @{ Expression = { $_.Candidate.Rank }; Ascending = $true }, @{ Expression = { $_.Version }; Ascending = $false } |
        Select-Object -First 1
    if ($normalOk) { return $normalOk }

    $sharedOk = @($validated | Where-Object { $_.Ok -and $_.Candidate.Rank -eq 40 })
    if ($sharedOk.Count -eq 1) { return $sharedOk[0] }
    if ($sharedOk.Count -gt 1) {
        $list = ($sharedOk | ForEach-Object { " - {0} ({1})" -f $_.Candidate.Path, $_.Version }) -join [Environment]::NewLine
        throw "More than one compatible Python was found on the shared drive, so none was selected automatically. Create python_path.txt next to Setup.cmd with exactly one approved python.exe path.$([Environment]::NewLine)$list"
    }

    $badList = ($validated | Select-Object -First 10 | ForEach-Object { " - {0}: {1}" -f $_.Candidate.Path, $_.Reason }) -join [Environment]::NewLine
    throw "No compatible Python was found. Python $MinimumPython or newer is required, with the venv module available. Package compatibility is verified during setup.$([Environment]::NewLine)$badList"
}

function Get-VenvPython {
    Join-Path $VenvPath "Scripts\python.exe"
}

function Get-VenvPythonw {
    $pythonw = Join-Path $VenvPath "Scripts\pythonw.exe"
    if (Test-Path -LiteralPath $pythonw -PathType Leaf) { return $pythonw }
    Get-VenvPython
}

function Read-State {
    if (-not (Test-Path -LiteralPath $StatePath -PathType Leaf)) { return $null }
    try { Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json } catch { return $null }
}

function Remove-CurrentUserEnvironment {
    param([string]$Reason)
    Write-Info "Rebuilding this user's environment: $Reason"
    $resolvedEnv = [System.IO.Path]::GetFullPath($VenvPath)
    $resolvedRoot = [System.IO.Path]::GetFullPath($EnvRoot)
    if (-not $resolvedEnv.StartsWith($resolvedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove an environment outside the current user's environment folder."
    }
    if (Test-Path -LiteralPath $VenvPath) {
        Remove-Item -LiteralPath $VenvPath -Recurse -Force
    }
    if (Test-Path -LiteralPath $StatePath) {
        Remove-Item -LiteralPath $StatePath -Force
    }
}

function Ensure-Pip {
    param([string]$PythonPath)
    $pipCheck = Invoke-External -FilePath $PythonPath -Arguments @("-m", "pip", "--version") -Description "Checking pip in the environment" -AllowFailure
    if ($pipCheck.ExitCode -eq 0) { return }
    Write-Info "pip is missing from the environment. Trying Python ensurepip."
    $ensure = Invoke-External -FilePath $PythonPath -Arguments @("-m", "ensurepip", "--upgrade") -Description "Recovering pip with ensurepip" -AllowFailure
    if ($ensure.ExitCode -ne 0) {
        throw "pip is not available, and this Python cannot recover it with ensurepip. Ask support for an approved Python build that includes pip or ensurepip."
    }
    Invoke-External -FilePath $PythonPath -Arguments @("-m", "pip", "--version") -Description "Verifying pip after ensurepip" | Out-Null
}

function Test-RecoverableInstallFailure {
    param([string]$Output)
    if (-not $Output) { return $false }
    if ($Output -match "No matching distribution|Could not find a version|CERTIFICATE_VERIFY_FAILED|ProxyError|Access is denied|WinError 5") { return $false }
    $patterns = @(
        "(?is)(No such file or directory|The system cannot find the file specified|WinError 2).*(\.whl|pip-|temp|cache)",
        "(?is)(\.whl|pip-|temp|cache).*(No such file or directory|The system cannot find the file specified|WinError 2)",
        "(?i)(invalid wheel|wheel .* is invalid|corrupt.*cache)"
    )
    foreach ($pattern in $patterns) {
        if ($Output -match $pattern) { return $true }
    }
    $false
}

function Install-Requirements {
    param([string]$PythonPath)
    $tempRoot = Join-Path $UserBase ("tmp\{0}" -f ([guid]::NewGuid().ToString("N")))
    $pipCache = Join-Path $UserBase "pip-cache"
    New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
    New-Item -ItemType Directory -Path $pipCache -Force | Out-Null
    $oldTemp = $env:TEMP
    $oldTmp = $env:TMP
    $oldPipCache = $env:PIP_CACHE_DIR
    try {
        $env:TEMP = $tempRoot
        $env:TMP = $tempRoot
        $env:PIP_CACHE_DIR = $pipCache

        $upgrade = Invoke-External -FilePath $PythonPath -Arguments @("-m", "pip", "install", "--upgrade", "pip") -Description "Checking for a current pip" -AllowFailure
        if ($upgrade.ExitCode -ne 0) {
            Write-Info "pip could not be upgraded from the configured package source. Continuing with the available pip because package installation may still work."
        }

        $install = Invoke-External -FilePath $PythonPath -Arguments @("-m", "pip", "install", "--requirement", $RequirementsPath) -Description "Installing workflow packages" -AllowFailure
        if ($install.ExitCode -ne 0) {
            if (Test-RecoverableInstallFailure -Output $install.Output) {
                Write-Info "Package installation failed in a way that can be caused by a missing temporary wheel or stale cache. Retrying once with a fresh per-user temp folder and no pip cache."
                Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
                $tempRoot = Join-Path $UserBase ("tmp\{0}" -f ([guid]::NewGuid().ToString("N")))
                New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
                $env:TEMP = $tempRoot
                $env:TMP = $tempRoot
                $retry = Invoke-External -FilePath $PythonPath -Arguments @("-m", "pip", "install", "--no-cache-dir", "--requirement", $RequirementsPath) -Description "Retrying package installation without pip cache" -AllowFailure
                if ($retry.ExitCode -ne 0) {
                    throw "Package installation failed after one retry. The diagnostic log contains the pip output."
                }
            } else {
                throw "Package installation failed. The diagnostic log contains the pip output."
            }
        }

        Invoke-External -FilePath $PythonPath -Arguments @("-m", "pip", "check") -Description "Checking installed package compatibility" | Out-Null
        $verifyCode = "import openpyxl, PIL, fitz, docx, reportlab, playwright; import pythoncom, win32com.client; print('All required imports are available.')"
        Invoke-External -FilePath $PythonPath -Arguments @("-c", $verifyCode) -Description "Verifying required Python packages can be imported" | Out-Null
    } finally {
        $env:TEMP = $oldTemp
        $env:TMP = $oldTmp
        if ($null -eq $oldPipCache) { Remove-Item Env:\PIP_CACHE_DIR -ErrorAction SilentlyContinue } else { $env:PIP_CACHE_DIR = $oldPipCache }
        Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Test-InstalledRequirements {
    param([string]$PythonPath)
    $pipCheck = Invoke-External -FilePath $PythonPath -Arguments @("-m", "pip", "check") -Description "Checking installed package compatibility" -AllowFailure
    if ($pipCheck.ExitCode -ne 0) { return $false }
    $verifyCode = "import openpyxl, PIL, fitz, docx, reportlab, playwright; import pythoncom, win32com.client; print('All required imports are available.')"
    $importCheck = Invoke-External -FilePath $PythonPath -Arguments @("-c", $verifyCode) -Description "Verifying required Python packages can be imported" -AllowFailure
    return ($importCheck.ExitCode -eq 0)
}

function New-EnvironmentState {
    param($PythonInfo)
    [pscustomobject]@{
        project_root = $ProjectRoot
        source_python = $PythonInfo.Candidate.Path
        source_python_version = $PythonInfo.Version.ToString()
        requirements_sha256 = Get-FileHashText $RequirementsPath
        created_utc = [DateTime]::UtcNow.ToString("o")
    } | ConvertTo-Json | Set-Content -LiteralPath $StatePath -Encoding ASCII
}

function Ensure-Environment {
    if (-not (Test-Path -LiteralPath $EntryPointPath -PathType Leaf)) {
        throw "The application entry point is missing: app.py"
    }
    if (-not (Test-Path -LiteralPath $RequirementsPath -PathType Leaf)) {
        throw "The requirements file is missing: requirements.txt"
    }

    $pythonInfo = Find-Python
    $pythonPath = Get-VenvPython
    $requirementsHash = Get-FileHashText $RequirementsPath
    $state = Read-State
    $mustCreate = $false
    $mustInstall = $false

    if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
        $mustCreate = $true
        $mustInstall = $true
    } elseif ($null -eq $state) {
        $mustCreate = $true
        $mustInstall = $true
        Remove-CurrentUserEnvironment -Reason "environment metadata is missing"
    } elseif ($state.source_python -ine $pythonInfo.Candidate.Path -or $state.source_python_version -ne $pythonInfo.Version.ToString()) {
        $mustCreate = $true
        $mustInstall = $true
        Remove-CurrentUserEnvironment -Reason "it was created with a different Python interpreter"
    } elseif ($state.requirements_sha256 -ne $requirementsHash) {
        Write-Info "requirements.txt changed; this user's existing environment will be updated."
        $mustInstall = $true
    }

    if (-not $mustCreate) {
        $runtime = Invoke-External -FilePath $pythonPath -Arguments @("-c", "import sys; print(sys.version)") -Description "Checking the environment can run" -AllowFailure
        if ($runtime.ExitCode -ne 0) {
            Remove-CurrentUserEnvironment -Reason "its Python cannot run"
            $mustCreate = $true
            $mustInstall = $true
        }
    }

    if ($mustCreate) {
        if (Test-Path -LiteralPath $VenvPath) {
            Remove-CurrentUserEnvironment -Reason "the environment is incomplete or stale"
        }
        Write-Info ("Creating a per-user environment at: {0}" -f $VenvPath)
        Invoke-External -FilePath $pythonInfo.Candidate.Path -Arguments @("-m", "venv", $VenvPath) -Description "Creating virtual environment" | Out-Null
    } else {
        Write-Info ("Reusing this user's environment at: {0}" -f $VenvPath)
    }

    $pythonPath = Get-VenvPython
    if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
        throw "The virtual environment was not created correctly because python.exe is missing."
    }

    Ensure-Pip -PythonPath $pythonPath
    if (-not $mustInstall) {
        if (Test-InstalledRequirements -PythonPath $pythonPath) {
            Write-Info "This user's existing environment is healthy."
        } else {
            Write-Info "This user's environment is missing or has incompatible packages. Repairing it now."
            $mustInstall = $true
        }
    }
    if ($mustInstall) {
        Install-Requirements -PythonPath $pythonPath
    }
    New-EnvironmentState -PythonInfo $pythonInfo
    Write-Info ""
    Write-Info "Setup is complete for this Windows user."
    Write-Info ("Python selected: {0} ({1})" -f $pythonInfo.Candidate.Path, $pythonInfo.Version)
    Write-Info ("Per-user environment: {0}" -f $VenvPath)
    Write-Info ("Diagnostic log: {0}" -f $LogPath)
}

function Use-EnvironmentLock {
    param([scriptblock]$Body)
    $lockPath = Join-Path $EnvRoot "environment.lock"
    $lock = $null
    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    while ($null -eq $lock) {
        try {
            $lock = [System.IO.File]::Open($lockPath, [System.IO.FileMode]::OpenOrCreate, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
        } catch {
            if ($stopwatch.Elapsed.TotalSeconds -gt 120) {
                throw "Another setup or startup is still using this user's environment. Close other launch windows and try again."
            }
            Write-Info "Waiting for another setup or startup window to finish using this user's environment..."
            Start-Sleep -Seconds 2
        }
    }
    try {
        & $Body
    } finally {
        if ($lock) { $lock.Dispose() }
    }
}

function Start-App {
    param([string[]]$Arguments)
    $pythonw = Get-VenvPythonw
    $argText = @()
    foreach ($argument in $Arguments) {
        $argText += ('"{0}"' -f ($argument.Replace('"', '\"')))
    }
    Start-Process -FilePath $pythonw -WorkingDirectory $ProjectRoot -ArgumentList $argText -WindowStyle Hidden
}

try {
    Write-Info $ProjectName
    Write-Info ("Project folder: {0}" -f $ProjectRoot)
    Write-Info ("Diagnostic log: {0}" -f $LogPath)

    switch ($Action) {
        "Setup" {
            Use-EnvironmentLock { Ensure-Environment }
            Write-Info "The browser interface uses available Windows fonts. No font download is required."
        }
        "Start" {
            Use-EnvironmentLock { Ensure-Environment }
            Start-App -Arguments @($EntryPointPath)
        }
        "StartDemo" {
            Use-EnvironmentLock { Ensure-Environment }
            $python = Get-VenvPython
            $demoConfig = Join-Path $ProjectRoot "demo\config.json"
            if (-not (Test-Path -LiteralPath $demoConfig -PathType Leaf)) {
                Invoke-External -FilePath $python -Arguments @("-m", "workflow.demo", "prepare") -Description "Preparing demo configuration" | Out-Null
            }
            $liveDemoConfig = Join-Path $ProjectRoot "demo\live\config.json"
            if (Test-Path -LiteralPath $liveDemoConfig -PathType Leaf) {
                $demoConfig = $liveDemoConfig
            }
            Start-App -Arguments @($EntryPointPath, "--config", $demoConfig)
        }
        "Test" {
            Use-EnvironmentLock { Ensure-Environment }
            $env:PYTHONDONTWRITEBYTECODE = "1"
            Invoke-External -FilePath (Get-VenvPython) -Arguments @("-m", "unittest", "discover", "-s", "tests", "-v") -Description "Running workflow tests" | Out-Null
        }
    }
    Stop-Logging
    exit 0
} catch {
    Write-Info ""
    Write-Info "The requested action did not finish."
    Write-Info $_.Exception.Message
    Write-Info ""
    Write-Info "What to try next:"
    Write-Info "1. Make sure the shared drive is connected and this folder is writable enough to read the project files."
    Write-Info "2. If Python was not found or more than one shared Python was found, create python_path.txt next to Setup.cmd with the full path to the approved python.exe."
    Write-Info "3. If package installation failed, send the diagnostic log path below to support. The script keeps package sources and proxy settings controlled by pip and company policy."
    Write-Info ("Diagnostic log: {0}" -f $LogPath)
    Stop-Logging
    exit 1
}
