[CmdletBinding()]
param(
    [ValidateRange(5, 3600)]
    [int]$IntervalSeconds = 10,
    [ValidateRange(1, 60)]
    [int]$LocalIdleGuardSeconds = 10,
    [ValidateRange(1, 24)]
    [int]$RunHours = 8,
    [string]$WindowTitle = 'Operations Pool'
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Text;

public static class NativeWindowInput
{
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

    [StructLayout(LayoutKind.Sequential)]
    public struct LASTINPUTINFO { public uint cbSize; public uint dwTime; }

    [StructLayout(LayoutKind.Sequential)]
    public struct INPUT { public uint type; public InputUnion U; }

    [StructLayout(LayoutKind.Explicit)]
    public struct InputUnion
    {
        [FieldOffset(0)] public KEYBDINPUT ki;
        [FieldOffset(0)] public MOUSEINPUT mi;
        [FieldOffset(0)] public HARDWAREINPUT hi;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct KEYBDINPUT
    {
        public ushort wVk; public ushort wScan; public uint dwFlags;
        public uint time; public UIntPtr dwExtraInfo;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct MOUSEINPUT
    {
        public int dx; public int dy; public uint mouseData;
        public uint dwFlags; public uint time; public UIntPtr dwExtraInfo;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct HARDWAREINPUT { public uint uMsg; public ushort wParamL; public ushort wParamH; }

    [DllImport("user32.dll")]
    public static extern bool EnumWindows(EnumWindowsProc callback, IntPtr lParam);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int maxCount);
    [DllImport("user32.dll")]
    public static extern bool IsWindowVisible(IntPtr hWnd);
    [DllImport("user32.dll")]
    public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")]
    public static extern bool ShowWindowAsync(IntPtr hWnd, int command);
    [DllImport("user32.dll")]
    public static extern uint SendInput(uint inputCount, INPUT[] inputs, int inputSize);
    [DllImport("user32.dll")]
    public static extern bool GetLastInputInfo(ref LASTINPUTINFO info);
    [DllImport("user32.dll")]
    public static extern IntPtr GetAncestor(IntPtr hWnd, uint flags);
    [DllImport("user32.dll")]
    public static extern bool PostMessage(IntPtr hWnd, uint message, IntPtr wParam, IntPtr lParam);
    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr hWnd, IntPtr processId);
    [DllImport("user32.dll")]
    public static extern bool GetGUIThreadInfo(uint threadId, ref GUITHREADINFO info);
    [DllImport("user32.dll")]
    public static extern uint MapVirtualKey(uint code, uint mapType);
    [DllImport("user32.dll")]
    public static extern IntPtr OpenInputDesktop(uint flags, bool inherit, uint desiredAccess);
    [DllImport("user32.dll")]
    public static extern bool SwitchDesktop(IntPtr desktop);
    [DllImport("user32.dll")]
    public static extern bool CloseDesktop(IntPtr desktop);
    [DllImport("kernel32.dll")]
    public static extern uint SetThreadExecutionState(uint flags);

    [StructLayout(LayoutKind.Sequential)]
    public struct GUITHREADINFO
    {
        public uint cbSize; public uint flags;
        public IntPtr hwndActive; public IntPtr hwndFocus; public IntPtr hwndCapture;
        public IntPtr hwndMenuOwner; public IntPtr hwndMoveSize; public IntPtr hwndCaret;
        public RECT rcCaret;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct RECT { public int left; public int top; public int right; public int bottom; }

    public const uint INPUT_KEYBOARD = 1;
    public const uint KEYEVENTF_KEYUP = 0x0002;
    public const ushort VK_F15 = 0x7E;
    public const int SW_RESTORE = 9;
    public const uint GA_ROOT = 2;
    public const uint WM_KEYDOWN = 0x0100;
    public const uint WM_KEYUP = 0x0101;
    public const uint DESKTOP_SWITCHDESKTOP = 0x0100;
    public const uint ES_CONTINUOUS = 0x80000000;
    public const uint ES_SYSTEM_REQUIRED = 0x00000001;

    public static double SecondsSinceLastInput()
    {
        LASTINPUTINFO info = new LASTINPUTINFO();
        info.cbSize = (uint)Marshal.SizeOf(info);
        if (!GetLastInputInfo(ref info)) return 0;
        return unchecked((uint)Environment.TickCount - info.dwTime) / 1000.0;
    }

    public static bool PressF15()
    {
        INPUT[] inputs = new INPUT[2];
        inputs[0].type = INPUT_KEYBOARD;
        inputs[0].U.ki.wVk = VK_F15;
        inputs[1].type = INPUT_KEYBOARD;
        inputs[1].U.ki.wVk = VK_F15;
        inputs[1].U.ki.dwFlags = KEYEVENTF_KEYUP;
        return SendInput(2, inputs, Marshal.SizeOf(typeof(INPUT))) == 2;
    }

    public static bool HaveSameRoot(IntPtr first, IntPtr second)
    {
        if (first == IntPtr.Zero || second == IntPtr.Zero) return false;
        return GetAncestor(first, GA_ROOT) == GetAncestor(second, GA_ROOT);
    }

    public static bool IsWorkstationLocked()
    {
        IntPtr desktop = OpenInputDesktop(0, false, DESKTOP_SWITCHDESKTOP);
        if (desktop == IntPtr.Zero) return true;
        bool available = SwitchDesktop(desktop);
        CloseDesktop(desktop);
        return !available;
    }

    // Sends directly to the Horizon UI thread. Unlike SendInput, this can queue
    // a message to the user's desktop while the secure lock desktop is displayed.
    public static bool PostF15(IntPtr target)
    {
        IntPtr destination = target;
        uint threadId = GetWindowThreadProcessId(target, IntPtr.Zero);
        GUITHREADINFO info = new GUITHREADINFO();
        info.cbSize = (uint)Marshal.SizeOf(info);
        if (threadId != 0 && GetGUIThreadInfo(threadId, ref info) && info.hwndFocus != IntPtr.Zero)
            destination = info.hwndFocus;

        uint scan = MapVirtualKey(VK_F15, 0);
        long down = 1L | ((long)scan << 16);
        long up = down | 0xC0000000L;
        bool first = PostMessage(destination, WM_KEYDOWN, (IntPtr)VK_F15, (IntPtr)down);
        bool second = PostMessage(destination, WM_KEYUP, (IntPtr)VK_F15, (IntPtr)up);
        return first && second;
    }

    public static void PreventSystemSleep(bool enabled)
    {
        SetThreadExecutionState(enabled ? ES_CONTINUOUS | ES_SYSTEM_REQUIRED : ES_CONTINUOUS);
    }
}
'@

function Find-WindowByTitle {
    param([string]$Title)
    $script:matchedWindow = [IntPtr]::Zero
    $callback = [NativeWindowInput+EnumWindowsProc]{
        param([IntPtr]$handle, [IntPtr]$state)
        if (-not [NativeWindowInput]::IsWindowVisible($handle)) { return $true }
        $caption = [Text.StringBuilder]::new(1024)
        [void][NativeWindowInput]::GetWindowText($handle, $caption, $caption.Capacity)
        if ($caption.ToString().Equals($Title, [StringComparison]::OrdinalIgnoreCase)) {
            $script:matchedWindow = $handle
            return $false
        }
        return $true
    }
    [void][NativeWindowInput]::EnumWindows($callback, [IntPtr]::Zero)
    return $script:matchedWindow
}

function Send-KeepAwakePulse {
    $target = Find-WindowByTitle -Title $WindowTitle
    if ($target -eq [IntPtr]::Zero) {
        return @{ Success = $false; Busy = $false; Message = "Waiting for '$WindowTitle' to open" }
    }

    $previous = [NativeWindowInput]::GetForegroundWindow()
    $horizonIsForeground = [NativeWindowInput]::HaveSameRoot($previous, $target)
    $idleSeconds = [NativeWindowInput]::SecondsSinceLastInput()

    if ([NativeWindowInput]::IsWorkstationLocked()) {
        if ([NativeWindowInput]::PostF15($target)) {
            return @{ Success = $true; Busy = $false; Background = $true; Locked = $true; Message = 'Background pulse queued while Windows is locked' }
        }
        return @{ Success = $false; Busy = $false; Background = $true; Locked = $true; Message = 'Locked-state background pulse could not be queued' }
    }

    # When another local application has focus, post directly to Horizon's UI
    # thread. This neither steals focus nor waits for unrelated local activity.
    if (-not $horizonIsForeground) {
        if ([NativeWindowInput]::PostF15($target)) {
            return @{ Success = $true; Busy = $false; Background = $true; Locked = $false; Message = 'Background pulse queued to Operations Pool' }
        }
        return @{ Success = $false; Busy = $false; Background = $true; Locked = $false; Message = 'Horizon did not accept the background pulse' }
    }

    # Activity only counts as VDI activity when Horizon actually owns the foreground.
    if ($horizonIsForeground -and $idleSeconds -lt $LocalIdleGuardSeconds) {
        return @{ Success = $false; Busy = $true; Background = $false; Locked = $false; Message = 'Manual activity in the VDI - pulse not needed yet' }
    }

    if (-not [NativeWindowInput]::HaveSameRoot([NativeWindowInput]::GetForegroundWindow(), $target)) {
        return @{ Success = $false; Busy = $false; Background = $false; Locked = $false; Message = 'Operations Pool changed focus; retrying shortly' }
    }

    $sent = [NativeWindowInput]::PressF15()
    Start-Sleep -Milliseconds 100
    if (-not $sent) {
        return @{ Success = $false; Busy = $false; Background = $false; Locked = $false; Message = 'Windows could not send the keep-awake pulse' }
    }
    return @{ Success = $true; Busy = $false; Background = $false; Locked = $false; Message = 'Operations Pool is being kept awake' }
}

function Format-Duration {
    param([TimeSpan]$Duration)
    $hours = [Math]::Max(0, [Math]::Floor($Duration.TotalHours))
    return '{0:00}:{1:00}:{2:00}' -f $hours, $Duration.Minutes, $Duration.Seconds
}

$logPath = Join-Path $PSScriptRoot 'OperationsPool-KeepAwake.log'
function Write-KeepAwakeLog {
    param([string]$Message)
    Add-Content -LiteralPath $logPath -Value ("{0:yyyy-MM-dd HH:mm:ss}  {1}" -f (Get-Date), $Message)
}

$normalColour = [Drawing.Color]::FromArgb(22, 128, 57)
$warningColour = [Drawing.Color]::FromArgb(218, 165, 32)
$white = [Drawing.Color]::White

$form = [Windows.Forms.Form]::new()
$form.Text = 'Operations Pool Keep-Awake'
$form.Size = [Drawing.Size]::new(430, 225)
$form.MinimumSize = $form.Size
$form.MaximumSize = $form.Size
$form.StartPosition = [Windows.Forms.FormStartPosition]::Manual
$workingArea = [Windows.Forms.Screen]::PrimaryScreen.WorkingArea
$form.Location = [Drawing.Point]::new($workingArea.Right - $form.Width - 20, $workingArea.Bottom - $form.Height - 20)
$form.BackColor = $normalColour
$form.ForeColor = $white
$form.TopMost = $false
$form.ShowInTaskbar = $true

$heading = [Windows.Forms.Label]::new()
$heading.Text = 'OPERATIONS POOL KEEP-AWAKE'
$heading.Font = [Drawing.Font]::new('Segoe UI Semibold', 13)
$heading.ForeColor = $white
$heading.BackColor = [Drawing.Color]::Transparent
$heading.TextAlign = [Drawing.ContentAlignment]::MiddleCenter
$heading.SetBounds(15, 12, 385, 30)
$form.Controls.Add($heading)

$remainingLabel = [Windows.Forms.Label]::new()
$remainingLabel.Text = ('Time remaining: {0:00}:00:00' -f $RunHours)
$remainingLabel.Font = [Drawing.Font]::new('Segoe UI Semibold', 22)
$remainingLabel.ForeColor = $white
$remainingLabel.BackColor = [Drawing.Color]::Transparent
$remainingLabel.TextAlign = [Drawing.ContentAlignment]::MiddleCenter
$remainingLabel.SetBounds(15, 47, 385, 47)
$form.Controls.Add($remainingLabel)

$statusLabel = [Windows.Forms.Label]::new()
$statusLabel.Text = "Looking for '$WindowTitle'..."
$statusLabel.Font = [Drawing.Font]::new('Segoe UI', 10)
$statusLabel.ForeColor = $white
$statusLabel.BackColor = [Drawing.Color]::Transparent
$statusLabel.TextAlign = [Drawing.ContentAlignment]::MiddleCenter
$statusLabel.SetBounds(15, 98, 385, 26)
$form.Controls.Add($statusLabel)

$lastPulseLabel = [Windows.Forms.Label]::new()
$lastPulseLabel.Text = 'Last automatic pulse: not sent yet'
$lastPulseLabel.Font = [Drawing.Font]::new('Segoe UI', 9)
$lastPulseLabel.ForeColor = $white
$lastPulseLabel.BackColor = [Drawing.Color]::Transparent
$lastPulseLabel.TextAlign = [Drawing.ContentAlignment]::MiddleCenter
$lastPulseLabel.SetBounds(15, 124, 385, 23)
$form.Controls.Add($lastPulseLabel)

$stopButton = [Windows.Forms.Button]::new()
$stopButton.Text = 'Stop and close'
$stopButton.Font = [Drawing.Font]::new('Segoe UI', 9)
$stopButton.ForeColor = [Drawing.Color]::Black
$stopButton.BackColor = [Drawing.Color]::White
$stopButton.UseVisualStyleBackColor = $false
$stopButton.SetBounds(145, 151, 125, 29)
$stopButton.Add_Click({ $form.Close() })
$form.Controls.Add($stopButton)

$startedAt = [DateTime]::Now
$endsAt = $startedAt.AddHours($RunHours)
$nextPulseAt = $startedAt
[NativeWindowInput]::PreventSystemSleep($true)
Write-KeepAwakeLog "Started. Pulse interval: $IntervalSeconds seconds. Scheduled end: $($endsAt.ToString('yyyy-MM-dd HH:mm:ss'))."

$timer = [Windows.Forms.Timer]::new()
$timer.Interval = 1000
$timer.Add_Tick({
    $now = [DateTime]::Now
    $remaining = $endsAt - $now

    if ($remaining.TotalSeconds -le 0) {
        $remainingLabel.Text = 'Time remaining: 00:00:00'
        $statusLabel.Text = 'Eight hours finished - close and run again'
        $form.BackColor = $warningColour
        $timer.Stop()
        return
    }

    $remainingLabel.Text = 'Time remaining: ' + (Format-Duration -Duration $remaining)
    if ($remaining.TotalMinutes -le 30) { $form.BackColor = $warningColour }
    else { $form.BackColor = $normalColour }

    if ($now -ge $nextPulseAt) {
        $result = Send-KeepAwakePulse
        $statusLabel.Text = $result.Message
        if ($result.Success) {
            $pulseMode = if ($result.Locked) { 'locked/background' } elseif ($result.Background) { 'background' } else { 'foreground input' }
            $lastPulseLabel.Text = 'Last pulse: ' + (Get-Date -Format 'HH:mm:ss') + " ($pulseMode)"
            Write-KeepAwakeLog "F15 pulse sent to Operations Pool ($pulseMode)."
            $script:nextPulseAt = [DateTime]::Now.AddSeconds($IntervalSeconds)
        }
        elseif (-not $result.Busy) {
            # Missing-window/focus errors retry promptly; active use retries each tick.
            $script:nextPulseAt = [DateTime]::Now.AddSeconds(10)
        }
    }
})

$form.Add_Shown({ $form.Activate(); $timer.Start() })
$form.Add_FormClosed({
    $timer.Stop()
    $timer.Dispose()
    [NativeWindowInput]::PreventSystemSleep($false)
    Write-KeepAwakeLog 'Stopped.'
})
try { [void]$form.ShowDialog() }
finally { [NativeWindowInput]::PreventSystemSleep($false) }
