param([switch]$AcceptLicense)
Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$stage = $null
$lock = $null
$logging = $false
try {
    if (-not $env:LOCALAPPDATA) { throw 'Windows has not provided a per-user local folder. Contact support.' }
    $root = Join-Path $env:LOCALAPPDATA 'CDDAuditRemediation\fonts'
    New-Item -ItemType Directory -Path $root -Force | Out-Null
    $log = Join-Path $root ("aptos-{0}-{1}.log" -f (Get-Date -Format 'yyyyMMdd-HHmmss'), $PID)
    Start-Transcript -LiteralPath $log | Out-Null
    $logging = $true
    Write-Host "Font diagnostic log: $log"
    try {
        $lock = [IO.File]::Open((Join-Path $root 'aptos.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
    } catch { throw 'Another font installation is running for this user. Close it and try again.' }
    $target = Join-Path $root 'Aptos-4.40'
    $hashes = @{
        'Aptos.ttf' = '01bbd2d3bd483045e1dbf4f106935cb86478b937f8d334258ad12eea60554a05'
        'Aptos-Bold.ttf' = 'ae318584be8737164e24842e0b27ab180ee6761c1bedd799f5a29c93a8a4e65c'
    }
    $healthy = Test-Path -LiteralPath (Join-Path $target 'Microsoft Aptos Fonts EULA.rtf') -PathType Leaf
    foreach ($name in $hashes.Keys) {
        $file = Join-Path $target $name
        if (-not (Test-Path -LiteralPath $file -PathType Leaf) -or
            (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash -ne $hashes[$name]) { $healthy = $false }
    }
    Add-Type -AssemblyName System.Drawing
    $collection = New-Object Drawing.Text.InstalledFontCollection
    try { $installed = @($collection.Families | Where-Object { $_.Name -eq 'Aptos' }).Count -gt 0 }
    finally { $collection.Dispose() }
    if ($installed) {
        Write-Host 'Windows already provides Aptos. No download or installation is needed.'
    } elseif ($healthy) {
        Write-Host 'This user already has the verified Aptos fonts. No download is needed.'
    } else {
        $stage = Join-Path $root ('install-' + [Guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $stage | Out-Null
        $archive = Join-Path $stage 'aptos.zip'
        Write-Host 'Downloading the official Microsoft Aptos font archive using your existing network settings...'
        Invoke-WebRequest -UseBasicParsing -TimeoutSec 60 -Uri 'https://download.microsoft.com/download/8/6/0/860a94fa-7feb-44ef-ac79-c072d9113d69/Microsoft%20Aptos%20Fonts.zip' -OutFile $archive
        if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne '6528FD120E719A9F985E94214ECA6887D1653B88456916A792A630B02E95B025') {
            throw 'The Microsoft archive differs from the approved version. Nothing was installed. Contact support.'
        }
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $zip = [IO.Compression.ZipFile]::OpenRead($archive)
        try {
            foreach ($name in @('Aptos.ttf', 'Aptos-Bold.ttf', 'Microsoft Aptos Fonts EULA.rtf')) {
                $entry = $zip.GetEntry($name)
                if ($null -eq $entry) { throw 'The font archive is incomplete. Nothing was installed.' }
                [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, (Join-Path $stage $name))
            }
        } finally { $zip.Dispose() }
        if (-not $AcceptLicense) {
            Add-Type -AssemblyName System.Windows.Forms
            $dialog = New-Object Windows.Forms.Form
            $dialog.Text = 'Microsoft Aptos font licence'
            $dialog.Width = 700
            $dialog.Height = 560
            $dialog.StartPosition = 'CenterScreen'
            $text = New-Object Windows.Forms.RichTextBox
            $text.Dock = 'Fill'
            $text.ReadOnly = $true
            $text.LoadFile((Join-Path $stage 'Microsoft Aptos Fonts EULA.rtf'))
            $accept = New-Object Windows.Forms.Button
            $accept.Text = 'Accept and install for this user'
            $accept.Dock = 'Bottom'
            $accept.Height = 44
            $accept.DialogResult = [Windows.Forms.DialogResult]::OK
            $dialog.Controls.Add($text)
            $dialog.Controls.Add($accept)
            $dialog.AcceptButton = $accept
            try { $accepted = $dialog.ShowDialog() -eq [Windows.Forms.DialogResult]::OK }
            finally { $dialog.Dispose() }
            if (-not $accepted) { throw 'The licence was not accepted. Aptos was not installed.' }
        }
        foreach ($name in $hashes.Keys) {
            if ((Get-FileHash -LiteralPath (Join-Path $stage $name) -Algorithm SHA256).Hash -ne $hashes[$name]) {
                throw 'Font verification failed. Nothing was installed.'
            }
        }
        New-Item -ItemType Directory -Path $target -Force | Out-Null
        foreach ($name in @('Aptos.ttf', 'Aptos-Bold.ttf', 'Microsoft Aptos Fonts EULA.rtf')) {
            $temporary = Join-Path $target ($name + '.' + [Guid]::NewGuid().ToString('N') + '.tmp')
            try {
                Copy-Item -LiteralPath (Join-Path $stage $name) -Destination $temporary
                Move-Item -LiteralPath $temporary -Destination (Join-Path $target $name) -Force
            } finally {
                if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
            }
        }
        Write-Host 'Aptos is installed for this user. Reopen CDD Audit Remediation to use it.'
        Write-Host 'No administrator access, registry changes or system-wide font installation was used.'
    }
    $exitCode = 0
} catch {
    Write-Host 'Aptos installation did not finish.'
    Write-Host $_.Exception.Message
    Write-Host 'If Microsoft downloads or private fonts are blocked in your VDI, ask IT to deploy Aptos through an approved route.'
    $exitCode = 1
} finally {
    if ($stage) {
        $resolvedRoot = [IO.Path]::GetFullPath($root).TrimEnd('\') + '\'
        $resolvedStage = [IO.Path]::GetFullPath($stage)
        if ($resolvedStage.StartsWith($resolvedRoot, [StringComparison]::OrdinalIgnoreCase) -and
            [IO.Path]::GetFileName($resolvedStage) -match '^install-[a-f0-9]{32}$') {
            Remove-Item -LiteralPath $resolvedStage -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
    if ($lock) { $lock.Dispose() }
    if ($logging) { Stop-Transcript | Out-Null }
}
exit $exitCode
