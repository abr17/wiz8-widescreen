# Helpers for "live" play (on top of game.ps1): held keys, a screenshot without the Windows
# notification corner, a downscaled copy for viewing.
#   . C:\dev\wiz8-ws\scripts\play\play.ps1
#   Start-Play            # games\ru, Wiz8Runtime.exe, canvas 768
#   Key 'W' 800           # hold the key for 0.8 s
#   Snap 'name'           # docs\screens\play\<time>-name.png (+ _small.png 1280x800)
. "$PSScriptRoot\game.ps1"
$script:GameDir = Join-Path $PSScriptRoot '..\..\games\ru' | Resolve-Path
$script:Exe = 'Wiz8Runtime'
$script:Layout = 'canvas'
$script:CanvasW = 768
Add-Type -AssemblyName System.Drawing
Add-Type -Namespace W8 -Name Kb -MemberDefinition @'
[DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, int flags, int extra);
[DllImport("user32.dll")] public static extern uint MapVirtualKey(uint code, uint type);
'@ -ErrorAction SilentlyContinue

function Start-Play { Quit-Wiz8; Start-Sleep 2; Start-Wiz8 }

$script:VK = @{ 'UP'=0x26; 'DOWN'=0x28; 'LEFT'=0x25; 'RIGHT'=0x27; 'SPACE'=0x20; 'ENTER'=0x0D; 'ESC'=0x1B;
                'TAB'=0x09; 'SHIFT'=0x10; 'CTRL'=0x11; 'HOME'=0x24; 'END'=0x23; 'PGUP'=0x21; 'PGDN'=0x22;
                'F1'=0x70; 'F2'=0x71; 'F5'=0x74; 'F9'=0x78; 'BACKSPACE'=0x08; 'BACKTICK'=0xC0;
                'ALT'=0x12; 'DEL'=0x2E; 'NUM2'=0x62; 'NUM5'=0x65; 'NUM8'=0x68; 'NUM0'=0x60 }
function VkOf([string]$k) { if ($script:VK.ContainsKey($k.ToUpper())) { return $script:VK[$k.ToUpper()] }; return [int][char]$k.ToUpper() }

# Hold a key for ms milliseconds (scan code too; the game reads DirectInput/messages).
function Key([string]$k, [int]$ms = 120) {
    Focus-Wiz8 | Out-Null
    if (-not (Test-Wiz8Foreground)) { Write-Warning "Key $k skipped: game is not in the foreground"; return }
    $vk = VkOf $k; $sc = [W8.Kb]::MapVirtualKey($vk, 0)
    $ext = if ($vk -in 0x21..0x28) { 1 } else { 0 }
    [W8.Kb]::keybd_event($vk, $sc, $ext, 0)
    Start-Sleep -Milliseconds $ms
    [W8.Kb]::keybd_event($vk, $sc, $ext -bor 2, 0)
    Start-Sleep -Milliseconds 80
}

# Combination: modifier (CTRL/SHIFT/ALT) + key.
function KeyCombo([string]$mod, [string]$k, [int]$ms = 120) {
    Focus-Wiz8 | Out-Null
    if (-not (Test-Wiz8Foreground)) { Write-Warning "KeyCombo $mod+$k skipped: game is not in the foreground"; return }
    $mv = VkOf $mod; $ms2 = [W8.Kb]::MapVirtualKey($mv, 0)
    $vk = VkOf $k; $sc = [W8.Kb]::MapVirtualKey($vk, 0)
    $ext = if ($vk -in 0x21..0x28) { 1 } else { 0 }
    [W8.Kb]::keybd_event($mv, $ms2, 0, 0); Start-Sleep -Milliseconds 60
    [W8.Kb]::keybd_event($vk, $sc, $ext, 0); Start-Sleep -Milliseconds $ms
    [W8.Kb]::keybd_event($vk, $sc, $ext -bor 2, 0); Start-Sleep -Milliseconds 60
    [W8.Kb]::keybd_event($mv, $ms2, 2, 0); Start-Sleep -Milliseconds 80
}

# Screenshot: full screen, but the Windows notification corner (bottom right) is painted black
# so pop-up messages do not end up in files. Plus a downscaled copy.
function Snap([string]$name = 'shot') {
    Focus-Wiz8 | Out-Null
    if (-not (Test-Wiz8Foreground)) { Write-Warning "Snap skipped: game is not in the foreground"; return $null }
    $b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
    $bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size)
    # Windows pop-up notification (light rectangle at the bottom right): if
    # this corner is light (the game is dark there), paint over the whole corner.
    $sum = 0; $n = 0
    for ($y = $b.Height - 230; $y -lt $b.Height - 60; $y += 8) { for ($x = $b.Width - 480; $x -lt $b.Width - 20; $x += 8) { $c = $bmp.GetPixel($x, $y); $sum += ($c.R + $c.G + $c.B) / 3; $n++ } }
    if (($sum / $n) -gt 110) { $g.FillRectangle([System.Drawing.Brushes]::Black, $b.Width - 560, $b.Height - 300, 560, 300); Write-Warning 'Snap: notification corner painted over' }
    $g.Dispose()
    $dir = Join-Path $PSScriptRoot '..\..\docs\screens\tour'
    New-Item -ItemType Directory -Force $dir | Out-Null
    $stamp = '{0:HHmmss}' -f (Get-Date)
    $file = Join-Path (Resolve-Path $dir) "$stamp-$name.png"
    $small = New-Object System.Drawing.Bitmap 1280, 800
    $g2 = [System.Drawing.Graphics]::FromImage($small)
    $g2.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBilinear
    $g2.DrawImage($bmp, 0, 0, 1280, 800); $g2.Dispose()
    $small.Save(($file -replace '\.png$', '_small.png'), [System.Drawing.Imaging.ImageFormat]::Png)
    $bmp.Save($file, [System.Drawing.Imaging.ImageFormat]::Png)
    $bmp.Dispose(); $small.Dispose()
    return ($file -replace '\.png$', '_small.png')
}

# Screenshot taken by the game itself (Wiz8Runtime.exe): request file wiz8shot.req -> the game writes
# Wiz8NNNNN.JPG from the render buffer. Works even with the monitor off (when
# a Windows screen capture is black). Returns the path of the downscaled copy.
function GShot([string]$name = 'shot') {
    $dir = Join-Path $PSScriptRoot '..\..\docs\screens\tour'; New-Item -ItemType Directory -Force $dir | Out-Null; $dir = Resolve-Path $dir
    $before = @(Get-ChildItem -LiteralPath $script:GameDir -Filter 'Wiz8*.JPG' | ForEach-Object Name)
    New-Item -ItemType File -Force -Path (Join-Path $script:GameDir 'wiz8shot.req') | Out-Null
    $new = $null
    for ($i = 0; $i -lt 40 -and -not $new; $i++) {
        Start-Sleep -Milliseconds 150
        $new = Get-ChildItem -LiteralPath $script:GameDir -Filter 'Wiz8*.JPG' | Where-Object { $before -notcontains $_.Name } | Select-Object -First 1
    }
    if (-not $new) { Write-Warning 'GShot: the game did not save a frame'; return $null }
    Start-Sleep -Milliseconds 300
    $stamp = '{0:HHmmss}' -f (Get-Date)
    $file = Join-Path $dir "$stamp-$name.jpg"
    Move-Item -LiteralPath $new.FullName -Destination $file -Force
    $img = [System.Drawing.Image]::FromFile($file)
    $small = New-Object System.Drawing.Bitmap 1280, 800
    $g2 = [System.Drawing.Graphics]::FromImage($small)
    $g2.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBilinear
    $g2.DrawImage($img, 0, 0, 1280, 800); $g2.Dispose(); $img.Dispose()
    $out = $file -replace '\.jpg$', '_small.png'
    $small.Save($out, [System.Drawing.Imaging.ImageFormat]::Png); $small.Dispose()
    return $out
}

# Reads gXStatus flags from Wiz8Runtime.exe memory (address from build\vc2022\Wiz8Runtime.map,
# offsets from include\wiz8\xstatus.h): 0x8dc fCombatMode, 0x8df fNpcDialogueMode,
# 0x8e3 fCampMode. Only reads our own game.
Add-Type -Namespace W8 -Name Mem2 -MemberDefinition @'
[DllImport("kernel32.dll")] public static extern System.IntPtr OpenProcess(int access, bool inherit, int pid);
[DllImport("kernel32.dll")] public static extern bool ReadProcessMemory(System.IntPtr h, System.IntPtr addr, byte[] buf, int size, out int read);
[DllImport("kernel32.dll")] public static extern bool CloseHandle(System.IntPtr h);
'@ -ErrorAction SilentlyContinue
function XStatusBase {
    $map = Join-Path $PSScriptRoot '..\..\build\vc2022\Wiz8Runtime.map'
    $line = Select-String -Path $map -Pattern '\?gXStatus@@3UW8XStatus@@A' | Select-Object -First 1
    if (-not $line) { return 0 }
    return [Convert]::ToInt64(($line.Line -split '\s+')[3], 16)
}
function XFlag([int]$offset) {
    $p = Get-Process Wiz8Runtime -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $p) { return $null }
    if (-not $script:XBase) { $script:XBase = XStatusBase }
    $h = [W8.Mem2]::OpenProcess(0x0410, $false, $p.Id); $b = New-Object byte[] 1; $n = 0
    [void][W8.Mem2]::ReadProcessMemory($h, [IntPtr]($script:XBase + $offset), $b, 1, [ref]$n)
    [void][W8.Mem2]::CloseHandle($h)
    return $b[0] -ne 0
}
function InCombat { XFlag 0x8dc }
function InDialogue { XFlag 0x8df }

# Party position and heading from the game camera: g_gd_camera -> m_yaw +0x004, m_position +0x08c
# (include\wiz8\engine_code\GDCamera.h). g_startup_world is no good: it is a probe
# navigator for traces, its yaw jumps every frame.
function MapSymbol([string]$pattern) {
    $map = Join-Path $PSScriptRoot '..\..\build\vc2022\Wiz8Runtime.map'
    $line = Select-String -Path $map -Pattern $pattern | Select-Object -First 1
    if (-not $line) { return 0 }
    return [Convert]::ToInt64(($line.Line -split '\s+')[3], 16)
}
function ReadMem([long]$addr, [int]$size) {
    $p = Get-Process Wiz8Runtime -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $p) { return $null }
    $h = [W8.Mem2]::OpenProcess(0x0410, $false, $p.Id); $b = New-Object byte[] $size; $n = 0
    [void][W8.Mem2]::ReadProcessMemory($h, [IntPtr]$addr, $b, $size, [ref]$n)
    [void][W8.Mem2]::CloseHandle($h)
    return ,$b
}
function PartyPos {
    if (-not $script:CamPtr) { $script:CamPtr = MapSymbol '\?g_gd_camera@@3PAVGDCamera@@A' }
    $cam = [BitConverter]::ToUInt32((ReadMem $script:CamPtr 4), 0)
    if ($cam -eq 0) { return $null }
    $m = ReadMem $cam 0x98
    [pscustomobject]@{ X = [BitConverter]::ToSingle($m, 0x8c); Y = [BitConverter]::ToSingle($m, 0x90)
                       Z = [BitConverter]::ToSingle($m, 0x94); Yaw = [BitConverter]::ToSingle($m, 0x4) }
}

# Heading: forward = (sin yaw, cos yaw) in (X, Z); the right arrow increases yaw.
function AngleDiff([double]$from, [double]$to) {
    $d = ($to - $from) % (2 * [math]::PI)
    if ($d -gt [math]::PI) { $d -= 2 * [math]::PI }
    if ($d -lt -[math]::PI) { $d += 2 * [math]::PI }
    return $d
}
function TurnTo([double]$yaw) {
    for ($i = 0; $i -lt 12; $i++) {
        $d = AngleDiff (PartyPos).Yaw $yaw
        if ([math]::Abs($d) -lt 0.12) { return }
        $ms = [int][math]::Min(350, 40 + [math]::Abs($d) * 110)
        if ($d -gt 0) { Key 'RIGHT' $ms } else { Key 'LEFT' $ms }
        Start-Sleep -Milliseconds 250
    }
}
function TurnBy([double]$delta) { TurnTo ((PartyPos).Yaw + $delta) }
# Walk to point (X, Z) in a straight line; go around when blocked. Returns 'ARRIVED', 'COMBAT', 'STUCK'.
function GoTo([double]$x, [double]$z, [double]$tolerance = 600, [int]$maxSteps = 25) {
    $stuck = 0
    for ($i = 0; $i -lt $maxSteps; $i++) {
        $p = PartyPos
        $dx = $x - $p.X; $dz = $z - $p.Z
        if ([math]::Sqrt($dx * $dx + $dz * $dz) -lt $tolerance) { return 'ARRIVED' }
        TurnTo ([math]::Atan2($dx, $dz))
        Key 'UP' 900
        if (InCombat) { return 'COMBAT' }
        $q = PartyPos
        if ([math]::Sqrt([math]::Pow($q.X - $p.X, 2) + [math]::Pow($q.Z - $p.Z, 2)) -lt 150) {
            $stuck++
            if ($stuck -gt 4) { return 'STUCK' }
            TurnBy ((((Get-Random -Maximum 2) * 2) - 1) * 1.2); Key 'UP' 900
        } else { $stuck = 0 }
    }
    return 'STUCK'
}

# Explore: walk forward; when blocked (moved < 150 units) turn by a random angle.
# Stops when combat/dialogue starts. Returns 'COMBAT', 'DIALOGUE' or 'DONE'.
function Explore([int]$steps = 30) {
    for ($i = 0; $i -lt $steps; $i++) {
        $a = PartyPos
        Key 'UP' 1500
        if (InCombat) { return 'COMBAT' }
        if (InDialogue) { return 'DIALOGUE' }
        $b = PartyPos
        $d = [math]::Sqrt([math]::Pow($b.X - $a.X, 2) + [math]::Pow($b.Z - $a.Z, 2))
        if ($d -lt 150) {
            TurnBy (((Get-Random -Maximum 2) * 2 - 1) * (0.8 + (Get-Random -Maximum 100) / 50.0))
        } elseif ((Get-Random -Maximum 5) -eq 0) {
            TurnBy (((Get-Random -Maximum 2) * 2 - 1) * 0.5)
        }
    }
    return 'DONE'
}

# Wander until combat starts. Returns true if combat started.
function Wander([int]$steps = 20) {
    for ($i = 0; $i -lt $steps; $i++) {
        Key 'UP' (1500 + (Get-Random -Maximum 2000))
        if (InCombat) { return $true }
        if ((Get-Random -Maximum 3) -eq 0) { Key 'LEFT' (200 + (Get-Random -Maximum 600)) } else { Key 'RIGHT' (100 + (Get-Random -Maximum 300)) }
        if (InCombat) { return $true }
    }
    return $false
}

# Fight: press Enter (start a round) until combat ends or time runs out.
function FightOut([int]$maxSeconds = 600) {
    $sw = [Diagnostics.Stopwatch]::StartNew()
    while ((InCombat) -and $sw.Elapsed.TotalSeconds -lt $maxSeconds) {
        Key 'ENTER' 100; Start-Sleep 4
        if ((Alive) -eq 'DEAD') { return 'DEAD' }
    }
    if (InCombat) { return 'TIMEOUT' } else { return 'DONE' }
}

# Wait until the user has not touched the mouse/keyboard for at least sec seconds.
function Wait-Idle([int]$sec = 20, [int]$max = 600) {
    $t = 0; while ((Get-UserIdleSeconds) -lt $sec -and $t -lt $max) { Start-Sleep 5; $t += 5 }
}
function Alive { $p = Get-Process Wiz8Runtime -ErrorAction SilentlyContinue; if ($p) { $p.Refresh(); "alive responding=$($p.Responding)" } else { 'DEAD' } }
