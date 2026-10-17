# Helpers for testing the shipped patch (retail Wiz8.exe + version.dll + wiz8hy.dll).
#   . scripts\play\hybrid_session.ps1 [-GameDir games\work]
#   Start-Wiz8; Click640 626 444; Key 'ENTER'; T 'name'; Quit-Wiz8
# On top of play.ps1 / game.ps1 (Key, KeyCombo, Click640, RightClick640, Focus-Wiz8 ...):
# sets the exe to the retail Wiz8.exe and the mouse layout to the wide canvas, and adds
# T <name>: a client-area screenshot into docs\screens\tour\<name>.png with the Windows
# notification corner blanked if a notification is visible (never keep private info in files).
# The canvas width must match the game's choice (wiz8wide.log, "W="): 768 for 16:10, 856 for 16:9.
param([string]$GameDir = (Join-Path $PSScriptRoot '..\..\games\work'), [int]$CanvasW = 768)
$hsGameDir = (Resolve-Path $GameDir).Path; $hsCanvasW = $CanvasW
. "$PSScriptRoot\play.ps1"              # dot-sourcing resets GameDir/Exe/CanvasW, so set them after it
$script:GameDir = $hsGameDir
$script:Exe = 'Wiz8'
$script:Layout = 'canvas'
$script:CanvasW = $hsCanvasW

function T([string]$name) {
    $f = Join-Path $PSScriptRoot "..\..\docs\screens\tour\$name.png"
    New-Item -ItemType Directory -Force (Split-Path $f) | Out-Null
    Focus-Wiz8 | Out-Null
    pwsh -NoProfile -File (Join-Path $PSScriptRoot 'win_shot.ps1') $f -Width 1280 | Out-Null
    if (-not (Test-Path $f)) { Write-Warning "T: no screenshot (window minimised or not in front?)"; return $null }
    $bmp = [Drawing.Bitmap]::new($f); $bright = 0
    for ($x = $bmp.Width - 240; $x -lt $bmp.Width - 10; $x += 4) {
        for ($y = $bmp.Height - 270; $y -lt $bmp.Height - 30; $y += 4) {
            $c = $bmp.GetPixel($x, $y); if ($c.R -gt 235 -and $c.G -gt 235 -and $c.B -gt 235) { $bright++ }
        }
    }
    if ($bright -gt 200) {
        $copy = [Drawing.Bitmap]::new($bmp); $bmp.Dispose()
        $g = [Drawing.Graphics]::FromImage($copy)
        $g.FillRectangle([Drawing.Brushes]::Black, $copy.Width - 260, $copy.Height - 290, 260, 290); $g.Dispose()
        $copy.Save($f); $copy.Dispose(); Write-Warning 'T: notification corner blanked'
    } else { $bmp.Dispose() }
    (Resolve-Path $f).Path
}
