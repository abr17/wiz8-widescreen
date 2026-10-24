# Game control for automated tests: launch to the menu, clicks in 640x480 coordinates,
# loading the first save, quitting.
#   . C:\dev\wiz8-ws\scripts\play\game.ps1
#   Start-Wiz8; Load-FirstSave; Shot 'phase1'; Quit-Wiz8
# Important: in full-screen mode the game reads the mouse in screen pixels 0..640 x 0..480.
$script:GameDir = Join-Path $PSScriptRoot '..\..\games\work' | Resolve-Path
Add-Type -AssemblyName System.Windows.Forms
# Exe name without .exe: Wiz8 (original) or Wiz8Runtime (built from source)
$script:Exe = 'Wiz8'
Add-Type -Namespace W8 -Name In -MemberDefinition @'
[DllImport("user32.dll")] public static extern void mouse_event(int f,int x,int y,int d,int e);
[DllImport("user32.dll")] public static extern bool SetCursorPos(int x,int y);
[DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
[DllImport("user32.dll")] public static extern System.IntPtr GetForegroundWindow();
[DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(System.IntPtr h, out uint pid);
'@ -ErrorAction SilentlyContinue
[void][W8.In]::SetProcessDPIAware()
$script:Shell = New-Object -ComObject WScript.Shell

function Focus-Wiz8 { $p = Get-Process $script:Exe -ErrorAction SilentlyContinue; if ($p) { [void]$script:Shell.AppActivate($p.Id); Start-Sleep -Milliseconds 700 }; [bool]$p }
function Start-Wiz8([string[]]$Args = @()) {
    # no -ArgumentList when empty: Windows PowerShell 5.1 (e.g. inside Windows Sandbox) rejects an empty one
    $start = @{ FilePath = "$script:GameDir\$($script:Exe).exe"; WorkingDirectory = $script:GameDir; PassThru = $true }
    if ($Args) { $start.ArgumentList = $Args }
    $p = Start-Process @start
    Start-Sleep 10; Focus-Wiz8 | Out-Null
    if (Test-Wiz8Foreground) { $script:Shell.SendKeys('{ESC}') }   # one Esc skips the intro
    Start-Sleep 12; Focus-Wiz8 | Out-Null
    -not $p.HasExited
}
# How logical 640x480 coordinates map to the screen:
#   raw      — without the mouse patch (1 pixel = 1 unit, top-left corner);
#   stretch  — with the patch, UI stretched to the full screen;
#   centered — with the patch, 4:3 UI centered;
#   canvas   — Wiz8Runtime.exe with a wide canvas (wiz8wide.ini): a canvas of width
#              $script:CanvasW stretched to the full screen, the 640x480 window at its center.
$script:Layout = 'stretch'
$script:CanvasW = 768   # Wiz8Runtime: the W value from wiz8wide.log
function To-Screen([int]$x, [int]$y) {
    $b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
    switch ($script:Layout) {
        'raw' { return @($x, $y) }
        'canvas' { $W = $script:CanvasW; $ox = [int](($W - 640) / 2)
                   # center of the canvas pixel (as CanvasCanvasToScreen in Canvas.cpp)
                   return @([int][math]::Floor((2 * ($x + $ox) + 1) * $b.Width / (2 * $W)),
                            [int][math]::Floor((2 * $y + 1) * $b.Height / 960)) }
        'stretch' { return @([int][math]::Ceiling($x * $b.Width / 640 + 1), [int][math]::Ceiling($y * $b.Height / 480 + 1)) }
        'centered' { $bw = [int][math]::Round(640 * $b.Height / 480); $ox = [int](($b.Width - $bw) / 2)
                     return @([int]($ox + [math]::Ceiling($x * $bw / 640) + 1), [int][math]::Ceiling($y * $b.Height / 480 + 1)) }
    }
}
# How many seconds the user has not touched the mouse and keyboard (GetLastInputInfo).
# An automated test takes over the screen: run it only when the owner is away.
Add-Type -Namespace W8 -Name Idle -MemberDefinition @'
[StructLayout(LayoutKind.Sequential)] public struct LASTINPUTINFO { public uint cbSize; public uint dwTime; }
[DllImport("user32.dll")] public static extern bool GetLastInputInfo(ref LASTINPUTINFO plii);
public static uint IdleMs() { var i = new LASTINPUTINFO(); i.cbSize = (uint)System.Runtime.InteropServices.Marshal.SizeOf(i); GetLastInputInfo(ref i); return (uint)System.Environment.TickCount - i.dwTime; }
'@ -ErrorAction SilentlyContinue
function Get-UserIdleSeconds { [math]::Round([W8.Idle]::IdleMs() / 1000) }

# Is the game in the foreground? Otherwise a click/key would go to another window or the desktop.
function Test-Wiz8Foreground {
    $p = Get-Process $script:Exe -ErrorAction SilentlyContinue
    if (-not $p) { return $false }
    $procId = [uint32]0
    [void][W8.In]::GetWindowThreadProcessId([W8.In]::GetForegroundWindow(), [ref]$procId)
    return [bool]($p | Where-Object Id -eq $procId)
}
# Keys to the game (SendKeys format: '{ESC}', 'i'); skipped if the game is not in the foreground.
function Send-Wiz8Keys([string]$Keys) {
    Focus-Wiz8 | Out-Null
    if (-not (Test-Wiz8Foreground)) { Write-Warning "Send-Wiz8Keys $Keys skipped: game is not in the foreground"; return }
    $script:Shell.SendKeys($Keys)
}
function Click640([int]$x, [int]$y) {
    Focus-Wiz8 | Out-Null
    if (-not (Test-Wiz8Foreground)) { Write-Warning "Click640 $x,$y skipped: game is not in the foreground (or not running)"; return }
    $s = To-Screen $x $y
    [void][W8.In]::SetCursorPos($s[0], $s[1]); Start-Sleep -Milliseconds 250
    [W8.In]::mouse_event(2,0,0,0,0); Start-Sleep -Milliseconds 80; [W8.In]::mouse_event(4,0,0,0,0)
}
function RightClick640([int]$x, [int]$y) {
    Focus-Wiz8 | Out-Null
    if (-not (Test-Wiz8Foreground)) { Write-Warning "RightClick640 $x,$y skipped: game is not in the foreground"; return }
    $s = To-Screen $x $y
    [void][W8.In]::SetCursorPos($s[0], $s[1]); Start-Sleep -Milliseconds 250
    [W8.In]::mouse_event(8,0,0,0,0); Start-Sleep -Milliseconds 80; [W8.In]::mouse_event(16,0,0,0,0)
}
function Load-FirstSave { Click640 323 257; Start-Sleep 4; Click640 562 444; Start-Sleep 15; Focus-Wiz8 | Out-Null }
function Shot([string]$Folder = 'tmp') {
    Focus-Wiz8 | Out-Null
    # A screenshot without the game in front would capture other windows/the desktop - skip it.
    if (-not (Test-Wiz8Foreground)) { Write-Warning "Shot skipped: game is not in the foreground"; return }
    & "$PSScriptRoot\shot.ps1" -Folder $Folder
}
# Burst of screenshots for screens that flash by (level loading): $Count frames
# every $IntervalMs, only while the game is in the foreground; saved after the burst.
function Burst([string]$Folder = 'tmp', [int]$Count = 10, [int]$IntervalMs = 200) {
    Add-Type -AssemblyName System.Drawing
    $b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
    $frames = @()
    for ($i = 0; $i -lt $Count; $i++) {
        if (-not (Test-Wiz8Foreground)) { break }
        $bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height
        $g = [System.Drawing.Graphics]::FromImage($bmp)
        $g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size); $g.Dispose()
        $frames += $bmp
        Start-Sleep -Milliseconds $IntervalMs
    }
    $dir = Join-Path $PSScriptRoot "..\..\docs\screens\$Folder"
    New-Item -ItemType Directory -Force $dir | Out-Null
    $stamp = '{0:yyyyMMdd-HHmmss}' -f (Get-Date)
    for ($i = 0; $i -lt $frames.Count; $i++) {
        $file = Join-Path (Resolve-Path $dir) ("{0}-b{1:d2}.png" -f $stamp, $i)
        $frames[$i].Save($file, [System.Drawing.Imaging.ImageFormat]::Png); $frames[$i].Dispose()
        $file
    }
}
function Quit-Wiz8 {
    # A normal exit is not needed for tests: we do not save, just close the process.
    Get-Process $script:Exe -ErrorAction SilentlyContinue | Stop-Process -Force
}
