# Manual testing of the hybrid (original Wiz8.exe + wiz8hy.dll) with mouse and keyboard.
# The original reads the mouse as relative motion (DirectInput); SetCursorPos does not move its
# cursor, so we steer it with mouse_event moves using gusMouseXPos/YPos as feedback.
#   . scripts\play\play.ps1; . scripts\hybrid\hy_play.ps1
#   HyClick 640 775        # click in coordinates of the downscaled GShot screenshot (1280x800)
$script:GameDir = (Resolve-Path (Join-Path $PSScriptRoot '..\..\games\work')).Path
$script:Exe = 'Wiz8'
$script:HyMouseX = 0x006f050a   # gusMouseXPos (GLOBAL: WIZ8, sgp/input.cpp)
$script:HyMouseY = 0x006f04f8   # gusMouseYPos

function HyRead([long]$addr, [int]$size) {
    $p = Get-Process Wiz8 -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $p) { return $null }
    $h = [W8.Mem2]::OpenProcess(0x0410, $false, $p.Id); $b = New-Object byte[] $size; $n = 0
    [void][W8.Mem2]::ReadProcessMemory($h, [IntPtr]$addr, $b, $size, [ref]$n)
    [void][W8.Mem2]::CloseHandle($h)
    return , $b
}
function HyMouse {
    $x = HyRead $script:HyMouseX 2; $y = HyRead $script:HyMouseY 2
    if (-not $x) { return $null }
    # left of the 640 area (wide canvas) x is negative: read it as signed
    return @([BitConverter]::ToInt16($x, 0), [BitConverter]::ToInt16($y, 0))
}
# The game mouse is in 640x480 coordinates inside the 768x480 canvas (16:10, offset 64); the screenshot
# 1280x800 = canvas x 5/3: gx = sx*0.6 - 64, gy = sy*0.6 (like G in play_create.ps1).
function HyMoveTo([int]$gx, [int]$gy, [int]$tries = 40) {
    Focus-Wiz8 | Out-Null
    for ($i = 0; $i -lt $tries; $i++) {
        $m = HyMouse; if (-not $m) { return $false }
        $dx = $gx - $m[0]; $dy = $gy - $m[1]
        if ([math]::Abs($dx) -le 1 -and [math]::Abs($dy) -le 1) { return $true }
        # without Windows acceleration the steps are small; split large moves
        $sx = [math]::Max(-60, [math]::Min(60, [int]($dx / 2))); if ($sx -eq 0) { $sx = [math]::Sign($dx) }
        $sy = [math]::Max(-60, [math]::Min(60, [int]($dy / 2))); if ($sy -eq 0) { $sy = [math]::Sign($dy) }
        [W8.In]::mouse_event(1, $sx, $sy, 0, 0); Start-Sleep -Milliseconds 25
    }
    return $false
}
function HyClick([int]$sx, [int]$sy, [switch]$Right) {
    if (-not (Test-Wiz8Foreground)) { Focus-Wiz8 | Out-Null }
    if (-not (Test-Wiz8Foreground)) { Write-Warning "HyClick skipped: game is not in the foreground"; return }
    $ok = HyMoveTo ([int]($sx * 0.6 - 64)) ([int]($sy * 0.6))
    if (-not $ok) { Write-Warning "HyClick: cursor did not reach $sx,$sy (mouse $(HyMouse))" }
    Start-Sleep -Milliseconds 120
    if ($Right) { [W8.In]::mouse_event(8, 0, 0, 0, 0); Start-Sleep -Milliseconds 250; [W8.In]::mouse_event(16, 0, 0, 0, 0) }
    else { [W8.In]::mouse_event(2, 0, 0, 0, 0); Start-Sleep -Milliseconds 250; [W8.In]::mouse_event(4, 0, 0, 0, 0) }
    Start-Sleep -Milliseconds 150
}
