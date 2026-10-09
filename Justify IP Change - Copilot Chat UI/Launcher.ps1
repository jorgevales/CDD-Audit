param([ValidateSet('Setup','Start','Test')][string]$Action = 'Setup')

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$ProjectRoot = $PSScriptRoot
$ProjectName = 'Justify IP Change - Copilot Chat UI'
$MinimumPython = [version]'3.10'
$ProductionShare = ([System.IO.Path]::GetPathRoot($ProjectRoot) -ieq 'S:\')
$BootstrapSha256 = '9096EFA6E3A8457CC3EC56E749A2D1E17505B756EE3CB2B7E889526367EFC187'
$WindowsAccount = if ($env:USERNAME) { $env:USERNAME } else { [Environment]::UserName }
$LogPath = $null

foreach ($candidateRoot in @((Join-Path $ProjectRoot ('.setup-logs\' + $WindowsAccount)), (Join-Path ([System.IO.Path]::GetTempPath()) 'JustifyIPChange-SetupLogs'))) {
    try {
        New-Item -ItemType Directory -Path $candidateRoot -Force -ErrorAction Stop | Out-Null
        $candidateLog = Join-Path $candidateRoot ((Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + $PID + '-' + $Action + '.log')
        New-Item -ItemType File -Path $candidateLog -Force -ErrorAction Stop | Out-Null
        $LogPath = $candidateLog
        break
    } catch { }
}

function Write-RunLog([string]$Message) {
    $line = ('[{0}] {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss.fff'), $Message)
    Write-Host $line
    if ($script:LogPath) { try { Add-Content -LiteralPath $script:LogPath -Value $line -Encoding UTF8 -ErrorAction Stop } catch { } }
}

if (-not $LogPath) {
    Write-Host 'WARNING: No diagnostic log could be created. Check access to the project folder and Windows TEMP folder.'
} else {
    Write-RunLog ($ProjectName + ' launcher started.')
    Write-RunLog ('Action: ' + $Action)
    Write-RunLog ('Windows account: ' + $WindowsAccount)
    Write-RunLog ('Project folder: ' + $ProjectRoot)
    Write-RunLog ('Diagnostic log: ' + $LogPath)
}

function Invoke-NativeLogged([string]$Executable, [string[]]$Arguments, [string]$Description) {
    Write-RunLog $Description
    $priorPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $Executable @Arguments 2>&1 | ForEach-Object {
            $message = if ($_ -is [System.Management.Automation.ErrorRecord]) { $_.Exception.Message } else { [string]$_ }
            Write-RunLog $message
        }
        $commandExitCode = $LASTEXITCODE
    } finally { $ErrorActionPreference = $priorPreference }
    if ($commandExitCode -ne 0) { throw ($Description + ' failed with exit code ' + $commandExitCode + '. Existing files were retained; see the diagnostic log above.') }
}

function Test-Python([string]$Candidate, [bool]$RequireShared) {
    if (-not $Candidate) { return $false }
    $Candidate = $Candidate.Trim().Trim('"').Trim("'")
    if (Test-Path -LiteralPath $Candidate -PathType Container) { $Candidate = Join-Path $Candidate 'python.exe' }
    if (-not (Test-Path -LiteralPath $Candidate -PathType Leaf)) { return $false }
    $resolved = (Resolve-Path -LiteralPath $Candidate).Path
    if ($RequireShared -and [System.IO.Path]::GetPathRoot($resolved) -ine 'S:\') { return $false }
    $priorPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $versionText = & $resolved -B -E -s -c "import sys; print('.'.join(map(str, sys.version_info[:3])))" 2>$null
        if ($LASTEXITCODE -ne 0 -or [version]$versionText -lt $MinimumPython) { return $false }
    } finally { $ErrorActionPreference = $priorPreference }
    $script:SelectedPython = $resolved
    return $true
}

function Find-Python([bool]$RequireShared) {
    $configured = Join-Path $ProjectRoot 'python_path.txt'
    if (Test-Path -LiteralPath $configured -PathType Leaf) {
        $line = Get-Content -LiteralPath $configured -Encoding UTF8 | Where-Object { $_.Trim() -and -not $_.Trim().StartsWith('#') } | Select-Object -First 1
        if ($line -and (Test-Python $line $RequireShared)) { return $script:SelectedPython }
        throw 'python_path.txt does not identify an approved Python 3.10+ executable. On S: the complete Python installation must also be on S:.'
    }
    if (-not $RequireShared) {
        foreach ($name in @('python.exe','python3.exe')) {
            foreach ($command in @(Get-Command $name -All -ErrorAction SilentlyContinue)) {
                if (Test-Python $command.Source $false) { return $script:SelectedPython }
            }
        }
        $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
        if ($launcher) {
            foreach ($line in @(& $launcher.Source -0p 2>$null)) {
                if ($line -match '([A-Za-z]:\.+?python\.exe)\s*$' -and (Test-Python $Matches[1] $false)) { return $script:SelectedPython }
            }
        }
    }
    $nearby = [System.Collections.Generic.List[string]]::new()
    $cursor = [System.IO.DirectoryInfo]::new($ProjectRoot)
    for ($depth = 0; $depth -lt 5 -and $cursor; $depth++) {
        foreach ($folder in @('','Python','python','Shared Python')) { $nearby.Add((Join-Path $cursor.FullName $folder)) }
        $cursor = $cursor.Parent
    }
    foreach ($directory in $nearby) {
        if (Test-Python (Join-Path $directory 'python.exe') $RequireShared) { return $script:SelectedPython }
        if (Test-Python (Join-Path $directory 'Scripts\python.exe') $RequireShared) { return $script:SelectedPython }
    }
    if ($RequireShared -and (Test-Path -LiteralPath 'S:\' -PathType Container)) {
        Write-RunLog 'Finding shared Python on S: (bounded search; document contents are not read).'
        $queue = [System.Collections.Generic.Queue[object]]::new()
        $queue.Enqueue(@{ Path='S:\'; Depth=0 })
        $visited = 0
        while ($queue.Count -gt 0 -and $visited -lt 20000) {
            $item = $queue.Dequeue(); $visited++
            if (Test-Python (Join-Path $item.Path 'python.exe') $true) { return $script:SelectedPython }
            if ($item.Depth -ge 8) { continue }
            foreach ($child in @(Get-ChildItem -LiteralPath $item.Path -Directory -Force -ErrorAction SilentlyContinue)) {
                if (($child.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) { continue }
                if ($child.Name -in @('.git','node_modules','runtime','workspace','deliveries','Users')) { continue }
                if ($queue.Count -lt 20000) { $queue.Enqueue(@{ Path=$child.FullName; Depth=$item.Depth+1 }) }
            }
        }
    }
    throw 'Python 3.10 or newer was not found. Put an approved full python.exe path in python_path.txt beside Setup.cmd. Shared S: deployments require the complete Python installation on S:.'
}

function Test-WorkingPip([string]$Python) {
    $priorPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $Python -B -E -s -c 'import pip; from importlib.metadata import distribution; assert distribution(pip.__name__).version == pip.__version__' 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    } finally { $ErrorActionPreference = $priorPreference }
}

function Preserve-Environment([string]$EnvironmentPath) {
    $archive = Join-Path $ProjectRoot ('.venv-incomplete-' + [guid]::NewGuid().ToString('N'))
    $root = [System.IO.Path]::GetFullPath($ProjectRoot).TrimEnd('\') + '\'
    if (-not [System.IO.Path]::GetFullPath($EnvironmentPath).StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase)) { throw 'Environment recovery path is outside this project.' }
    Move-Item -LiteralPath $EnvironmentPath -Destination $archive -ErrorAction Stop
    Write-RunLog ('Preserved the incomplete environment at ' + $archive)
}

function Assert-Runtime([string]$Python, [bool]$RequireShared) {
    $mode = if ($RequireShared) { 'shared' } else { 'development' }
    $probe = @'
import ntpath
import sys
import sysconfig
from importlib.metadata import distribution

def is_shared(value):
    return isinstance(value, str) and ntpath.isabs(value) and ntpath.splitdrive(ntpath.normpath(value))[0].casefold() == 's:'

assert sys.version_info >= (3, 10), 'Python 3.10+ is required.'
if sys.argv[1] == 'shared':
    paths = {'running executable':sys.executable, 'base Python prefix':sys.base_prefix, 'base executable':getattr(sys,'_base_executable',sys.executable), 'standard library':sysconfig.get_path('stdlib')}
    bad = {name:value for name,value in paths.items() if not is_shared(value)}
    if bad: raise RuntimeError('Shared deployment requires the complete Python runtime on S:. Invalid runtime paths: '+repr(bad))
expected = {'et_xmlfile':'2.0.0','greenlet':'3.5.6','openpyxl':'3.1.5','playwright':'1.55.0','pyee':'13.0.1','typing_extensions':'4.16.0'}
for name, version in expected.items():
    package = distribution(name)
    if package.version != version: raise RuntimeError(f'{name}=={version} is required; found {package.version}.')
    if sys.argv[1] == 'shared' and not is_shared(str(package.locate_file(''))): raise RuntimeError(f'{name} is not installed on S:.')
print('Python runtime and pinned dependencies verified.')
'@
    Invoke-NativeLogged $Python @('-B','-E','-s','-c',$probe,$mode) 'Verifying the isolated Python runtime and pinned dependencies'
}

function Initialize-Environment([string]$BasePython) {
    $environmentPath = Join-Path $ProjectRoot '.venv'
    $environmentPython = Join-Path $environmentPath 'Scripts\python.exe'
    $requirements = Join-Path $ProjectRoot 'requirements.lock.txt'
    $bootstrap = Join-Path $ProjectRoot 'bootstrap\virtualenv.pyz'
    $lockPath = Join-Path $ProjectRoot '.venv-setup.lock'
    $setupLock = $null
    try {
        try { $setupLock = [System.IO.File]::Open($lockPath,[System.IO.FileMode]::OpenOrCreate,[System.IO.FileAccess]::ReadWrite,[System.IO.FileShare]::None) }
        catch { throw 'SETUP LOCKED: another user is already setting up this shared project, or the project is not writable. Wait for that setup to finish and retry.' }
        Write-RunLog ('Setup lock acquired: ' + $lockPath)
        if (Test-Path -LiteralPath $environmentPath) {
            if (-not (Test-Path -LiteralPath (Join-Path $environmentPath 'pyvenv.cfg') -PathType Leaf) -or -not (Test-Path -LiteralPath $environmentPython -PathType Leaf) -or -not (Test-WorkingPip $environmentPython)) {
                Write-RunLog 'The existing project environment is incomplete or has no working pip.'
                Preserve-Environment $environmentPath
            } else { Write-RunLog 'Reusing the existing shared project environment.' }
        }
        if (-not (Test-Path -LiteralPath $environmentPath)) {
            if (-not (Test-Path -LiteralPath $bootstrap -PathType Leaf)) { throw 'Bundled virtualenv bootstrap is missing. Restore the official repository files and retry.' }
            $actualHash = (Get-FileHash -LiteralPath $bootstrap -Algorithm SHA256).Hash
            if ($actualHash -ne $BootstrapSha256) { throw 'Bundled virtualenv bootstrap failed its SHA-256 check. Restore the official repository files and retry.' }
            Write-RunLog ('Bundled bootstrap verified: SHA256 ' + $actualHash)
            try {
                Invoke-NativeLogged $BasePython @('-B','-E','-s',$bootstrap,'--no-download','--no-periodic-update',$environmentPath) 'Creating the shared project environment'
                if (-not (Test-WorkingPip $environmentPython)) { throw 'Default virtualenv seeder did not create working pip.' }
            } catch {
                Write-RunLog ('Default seeder failed: ' + $_.Exception.Message)
                if (Test-Path -LiteralPath $environmentPath) { Preserve-Environment $environmentPath }
                Invoke-NativeLogged $BasePython @('-B','-E','-s',$bootstrap,'--no-download','--no-periodic-update','--seeder','pip',$environmentPath) 'Retrying environment creation with the direct pip seeder'
            }
        }
        if (-not (Test-WorkingPip $environmentPython)) { throw 'The project environment has no working pip after creation. Existing files were retained.' }
        if ($env:PIP_TARGET) { throw 'PIP_TARGET redirects installation. Clear it before Setup; no settings were changed.' }
        $priorPreference = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
        try { $pipConfig = @(& $environmentPython -B -E -s -m pip config list 2>&1); $pipExit = $LASTEXITCODE }
        finally { $ErrorActionPreference = $priorPreference }
        foreach ($line in $pipConfig) { Write-RunLog ([string]$line) }
        if ($pipExit -ne 0) { throw 'Unable to verify pip configuration.' }
        if (($pipConfig -join "`n") -match '(?im)^\s*[^=]*\.target\s*=') { throw 'Pip configuration redirects installation with target. Remove that override before Setup.' }
        Invoke-NativeLogged $environmentPython @('-B','-E','-s','-m','pip','install','--requirement',$requirements,'--disable-pip-version-check','--no-user','--prefix',$environmentPath) 'Installing exact dependencies from requirements.lock.txt'
        Invoke-NativeLogged $environmentPython @('-B','-E','-s','-m','pip','check') 'Checking package compatibility'
        return $environmentPython
    } finally { if ($setupLock) { $setupLock.Dispose(); Write-RunLog 'Setup lock released.' } }
}

try {
    $environmentPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
    if ($Action -eq 'Setup') {
        $basePython = Find-Python $ProductionShare
        Write-RunLog ('Using base Python: ' + $basePython)
        $python = Initialize-Environment $basePython
    } else {
        if (-not (Test-Path -LiteralPath $environmentPython -PathType Leaf)) { throw 'The shared project environment is not installed. Run Setup.cmd once, then retry.' }
        $python = $environmentPython
    }
    Assert-Runtime $python $ProductionShare
    $env:PYTHONDONTWRITEBYTECODE = '1'
    Push-Location -LiteralPath $ProjectRoot
    try {
        if ($Action -eq 'Start') {
            Write-RunLog 'Starting the application.'
            & $python -B -E -s (Join-Path $ProjectRoot 'app.py')
            $result = $LASTEXITCODE
        } elseif ($Action -eq 'Test') {
            Invoke-NativeLogged $python @('-B','-E','-s','-m','unittest','discover','-s','tests','-v') 'Running offline tests'
            $result = 0
        } else { Write-RunLog 'Setup completed successfully. This shared environment can now be used by VDI users.'; $result = 0 }
    } finally { Pop-Location }
    if ($result -ne 0) { throw ('The requested action stopped with exit code ' + $result + '.') }
    exit 0
} catch {
    Write-RunLog ('STOPPED: ' + $_.Exception.Message)
    if ($LogPath) { Write-Host ('Diagnostic log: ' + $LogPath) }
    exit 1
}
